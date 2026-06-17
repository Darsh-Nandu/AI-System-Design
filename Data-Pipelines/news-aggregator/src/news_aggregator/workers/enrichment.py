"""NLP enrichment — entity extraction, topic classification, volatility tagging."""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from typing import TYPE_CHECKING

import spacy
from spacy.language import Language

from news_aggregator.logging import get_logger
from news_aggregator.models import Entity, EnrichedArticle, PartitionTier, RawArticle
from news_aggregator.storage.redis_client import RedisStore

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

VOLATILE_TOPIC_KEYWORDS: set[str] = {
    "election", "elections", "vote", "voting", "ballot",
    "federal reserve", "rate decision", "interest rate",
    "breaking", "emergency", "attack", "explosion",
    "market crash", "stock market", "earnings",
    "war", "conflict", "ceasefire", "invasion",
    "earthquake", "hurricane", "tornado", "flood",
    "assassination", "coup",
}

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "politics": ["president", "congress", "senate", "parliament", "government", "election", "vote", "policy", "law"],
    "finance": ["stock", "market", "earnings", "federal reserve", "gdp", "inflation", "interest rate", "ipo", "fund"],
    "sports": ["championship", "tournament", "goal", "score", "match", "game", "player", "team", "season"],
    "technology": ["ai", "artificial intelligence", "startup", "software", "chip", "data", "cloud", "cybersecurity"],
    "health": ["vaccine", "drug", "clinical trial", "fda", "hospital", "pandemic", "outbreak", "treatment"],
    "climate": ["climate", "carbon", "emissions", "renewable", "solar", "wind", "fossil fuel", "temperature"],
    "breaking_news": ["breaking", "urgent", "flash", "just in", "developing"],
}


@lru_cache(maxsize=1)
def _load_nlp() -> Language:
    logger.info("loading_spacy_model", model="en_core_web_sm")
    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
    return nlp


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_entities(text: str) -> list[Entity]:
    nlp = _load_nlp()
    doc = nlp(text[:50_000])  # spaCy has a reasonable limit
    seen: set[tuple[str, str]] = set()
    entities = []
    for ent in doc.ents:
        if ent.label_ in {"PERSON", "ORG", "GPE", "NORP", "EVENT", "FAC", "LOC", "DATE"}:
            key = (ent.text.lower().strip(), ent.label_)
            if key not in seen:
                seen.add(key)
                entities.append(Entity(text=ent.text.strip(), label=ent.label_))
    return entities


def _build_fingerprint(entities: list[Entity]) -> str:
    key = sorted(f"{e.text.lower()}:{e.label}" for e in entities if e.label != "DATE")
    raw = "|".join(key)
    return hashlib.sha256(raw.encode()).hexdigest()[:16] if raw else ""


def _classify_topics(text: str) -> list[str]:
    text_lower = text.lower()
    matched = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(topic)
    return matched or ["general"]


def _is_volatile(topics: list[str], text: str) -> bool:
    if "breaking_news" in topics:
        return True
    text_lower = text.lower()
    return any(kw in text_lower for kw in VOLATILE_TOPIC_KEYWORDS)


def _assign_partition(is_volatile: bool) -> PartitionTier:
    return PartitionTier.HOT if is_volatile else PartitionTier.WARM


async def enrich(raw: RawArticle, redis: RedisStore) -> EnrichedArticle:
    """Full enrichment: clean → NLP → classify → fingerprint → partition."""
    from uuid import uuid4

    combined = f"{raw.title}. {raw.body}"
    cleaned = _clean_text(combined)

    entities = _extract_entities(cleaned)
    fingerprint = _build_fingerprint(entities)
    topics = _classify_topics(cleaned)
    volatile = _is_volatile(topics, cleaned)

    # Augment volatile check from Redis (editorial overrides)
    if not volatile and fingerprint:
        volatile = await redis.is_volatile_keyword(raw.title)

    partition = _assign_partition(volatile)

    enriched = EnrichedArticle(
        raw=raw,
        entities=entities,
        entity_fingerprint=fingerprint,
        topics=topics,
        is_volatile=volatile,
        partition=partition,
    )

    logger.debug(
        "article_enriched",
        url=raw.url,
        entities=len(entities),
        fingerprint=fingerprint,
        topics=topics,
        volatile=volatile,
        partition=partition.value,
    )
    return enriched
