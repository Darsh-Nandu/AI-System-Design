"""Redis client — entity fingerprint cache and volatile topics registry."""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from news_aggregator.config import get_settings

settings = get_settings()

VOLATILE_TOPICS_KEY = "volatile_topics"
FINGERPRINT_PREFIX = "fp:"


class RedisStore:
    def __init__(self) -> None:
        self._client: aioredis.Redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def set_fingerprint(self, fingerprint: str) -> None:
        """Record that we have seen this entity fingerprint."""
        await self._client.setex(
            f"{FINGERPRINT_PREFIX}{fingerprint}",
            settings.redis_fingerprint_ttl_seconds,
            "1",
        )

    async def has_fingerprint(self, fingerprint: str) -> bool:
        """True if we have seen this fingerprint before (Stage 1 pre-filter)."""
        return bool(await self._client.exists(f"{FINGERPRINT_PREFIX}{fingerprint}"))

    async def get_volatile_topic_keywords(self) -> list[str]:
        """Return all keywords for volatile topics (for partition routing)."""
        raw = await self._client.get(VOLATILE_TOPICS_KEY)
        if not raw:
            return []
        return json.loads(raw)

    async def set_volatile_topics(self, keywords: list[str]) -> None:
        await self._client.set(VOLATILE_TOPICS_KEY, json.dumps(keywords))

    async def is_volatile_keyword(self, keyword: str) -> bool:
        keywords = await self.get_volatile_topic_keywords()
        return any(kw.lower() in keyword.lower() for kw in keywords)

    async def close(self) -> None:
        await self._client.aclose()
