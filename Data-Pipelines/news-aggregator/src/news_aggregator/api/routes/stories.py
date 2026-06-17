"""Story cluster endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from news_aggregator.api.schemas import ArticleOut, EntityOut, StoryOut
from news_aggregator.storage.postgres import ArticleORM, StoryORM, get_session

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("/{story_id}", response_model=StoryOut)
async def get_story(
    story_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> StoryOut:
    story = await session.get(StoryORM, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    article_count_result = await session.scalars(
        select(ArticleORM).where(ArticleORM.story_id == story_id)
    )
    count = len(list(article_count_result.all()))

    return StoryOut(
        id=story.id,
        topic=story.topic,
        article_count=count,
        latest_article_id=story.latest_article_id,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


@router.get("/{story_id}/articles", response_model=list[ArticleOut])
async def get_story_articles(
    story_id: UUID,
    include_stale: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[ArticleOut]:
    q = select(ArticleORM).where(ArticleORM.story_id == story_id)
    if not include_stale:
        q = q.where(ArticleORM.stale == False)  # noqa: E712
    q = q.order_by(ArticleORM.published_at.desc())

    rows = await session.scalars(q)
    return [
        ArticleOut(
            id=r.id,
            url=r.url,
            source=r.source,
            title=r.title,
            published_at=r.published_at,
            processed_at=r.processed_at,
            topics=r.topics or [],
            entities=[EntityOut(**e) for e in (r.entities or [])],
            partition=r.partition,
            stale=r.stale,
            story_id=r.story_id,
            superseded_by=r.superseded_by,
            stale_at=r.stale_at,
        )
        for r in rows.all()
    ]
