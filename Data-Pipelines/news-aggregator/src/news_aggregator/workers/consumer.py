"""Kafka consumer — async worker group processing raw-articles topic."""

from __future__ import annotations

import asyncio
import signal

import orjson
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from news_aggregator.config import get_settings
from news_aggregator.invalidation.checker import run_cold_archiver, run_hot_checker
from news_aggregator.logging import configure_logging, get_logger
from news_aggregator.metrics import start_metrics_server
from news_aggregator.models import KafkaArticleMessage
from news_aggregator.storage.postgres import create_tables
from news_aggregator.storage.qdrant import QdrantStore
from news_aggregator.storage.redis_client import RedisStore
from news_aggregator.workers.pipeline import ArticlePipeline

settings = get_settings()
logger = get_logger(__name__)

_shutdown = asyncio.Event()


def _handle_signal(sig: int, _: object) -> None:
    logger.info("shutdown_signal_received", signal=sig)
    _shutdown.set()


async def _process_message(
    pipeline: ArticlePipeline,
    raw_value: bytes,
) -> None:
    try:
        data = orjson.loads(raw_value)
        msg = KafkaArticleMessage(**data)
        raw_article = msg.to_raw_article()
        await pipeline.process(raw_article)
    except Exception:
        logger.exception("message_processing_error")


async def consume() -> None:
    configure_logging()
    start_metrics_server(port=9100)

    await create_tables()

    qdrant = QdrantStore()
    redis = RedisStore()
    await qdrant.ensure_collections()

    pipeline = ArticlePipeline(qdrant=qdrant, redis=redis)

    consumer = AIOKafkaConsumer(
        settings.kafka_topic_raw_articles,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=settings.worker_batch_size,
        value_deserializer=lambda v: v,
    )

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    # Start background tasks
    hot_checker_task = asyncio.create_task(run_hot_checker(qdrant))
    cold_archiver_task = asyncio.create_task(run_cold_archiver())

    await consumer.start()
    logger.info(
        "consumer_started",
        topic=settings.kafka_topic_raw_articles,
        group=settings.kafka_consumer_group,
    )

    try:
        while not _shutdown.is_set():
            try:
                records = await asyncio.wait_for(
                    consumer.getmany(timeout_ms=1000, max_records=settings.worker_batch_size),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                continue

            tasks = []
            for _tp, messages in records.items():
                for msg in messages:
                    tasks.append(_process_message(pipeline, msg.value))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                await consumer.commit()

    except KafkaError:
        logger.exception("kafka_error")
    finally:
        hot_checker_task.cancel()
        cold_archiver_task.cancel()
        await consumer.stop()
        await qdrant.close()
        await redis.close()
        logger.info("consumer_stopped")


def run() -> None:
    asyncio.run(consume())


if __name__ == "__main__":
    run()
