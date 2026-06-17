"""Kafka producer — polls RSS scrapers and publishes to raw-articles topic."""

from __future__ import annotations

import argparse
import asyncio
import signal

import orjson
from aiokafka import AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from news_aggregator.config import get_settings
from news_aggregator.ingestion.scrapers.rss import SAMPLE_FEEDS, RSSFeedScraper
from news_aggregator.logging import configure_logging, get_logger
from news_aggregator.metrics import articles_ingested_total, start_metrics_server
from news_aggregator.models import KafkaArticleMessage, RawArticle

settings = get_settings()
logger = get_logger(__name__)

_shutdown = asyncio.Event()


async def _ensure_topic() -> None:
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
    await admin.start()
    try:
        existing = await admin.list_topics()
        if settings.kafka_topic_raw_articles not in existing:
            await admin.create_topics(
                [
                    NewTopic(
                        name=settings.kafka_topic_raw_articles,
                        num_partitions=settings.kafka_num_partitions,
                        replication_factor=settings.kafka_replication_factor,
                    )
                ]
            )
            logger.info("kafka_topic_created", topic=settings.kafka_topic_raw_articles)
    finally:
        await admin.close()


async def _publish(producer: AIOKafkaProducer, article: RawArticle) -> None:
    msg = KafkaArticleMessage(
        url=article.url,
        source=article.source,
        title=article.title,
        body=article.body,
        published_at=article.published_at.isoformat(),
        raw_tags=article.raw_tags,
    )
    value = orjson.dumps(msg.model_dump())
    # Partition by URL for deterministic routing
    key = article.url.encode()
    await producer.send(settings.kafka_topic_raw_articles, value=value, key=key)
    articles_ingested_total.labels(source=article.source).inc()


async def produce(seed: bool = False) -> None:
    configure_logging()
    start_metrics_server(port=9101)

    await _ensure_topic()

    scrapers = [RSSFeedScraper(f["url"], f["source"]) for f in SAMPLE_FEEDS]

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        compression_type="lz4",
        acks="all",
        enable_idempotence=True,
    )
    await producer.start()
    logger.info("producer_started", feeds=len(scrapers))

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, _: _shutdown.set())

    try:
        while not _shutdown.is_set():
            total = 0
            for scraper in scrapers:
                articles = await scraper.scrape()
                for article in articles:
                    await _publish(producer, article)
                    total += 1

            if total:
                logger.info("poll_cycle_complete", articles_published=total)

            if seed:
                logger.info("seed_mode_done")
                break

            await asyncio.sleep(settings.scraper_poll_interval_seconds)
    finally:
        await producer.stop()
        logger.info("producer_stopped")


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="Run one poll cycle and exit")
    args = parser.parse_args()
    asyncio.run(produce(seed=args.seed))


if __name__ == "__main__":
    run()
