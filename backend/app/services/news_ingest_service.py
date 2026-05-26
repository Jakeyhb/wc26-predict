from __future__ import annotations

import asyncio
from datetime import timedelta
from datetime import datetime
from pathlib import Path
from typing import Any

import feedparser
import httpx
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging import get_logger
from app.models import Match, NewsArticle, NewsSignal
from app.models.enums import ImpactDirection, ReviewStatus, SignalType
from app.schemas.admin import ManualSignalCreateRequest
from app.services.team_resolver import TeamResolver
from app.utils.datetime import utc_now
from app.utils.hash import sha256_text
from app.utils.http import fetch_json

settings = get_settings()
logger = get_logger(__name__)


async def build_match_keywords(db: AsyncSession, hours_ahead: int = 48) -> list[str]:
    """从未来比赛动态生成 GDELT 搜索关键词，使用 team_aliases 表。

    48h 内无比赛 → 扩大到 7 天 → 仍无比赛 → 返回空列表（不调 GDELT）。
    """
    from app.models import Team
    from app.models.enums import MatchStatus

    now = utc_now()
    cutoff = now + timedelta(hours=hours_ahead)

    result = await db.execute(
        select(Match).where(
            Match.status == MatchStatus.SCHEDULED,
            Match.match_date >= now,
            Match.match_date <= cutoff,
        )
    )
    matches = result.scalars().all()

    if not matches:
        cutoff = now + timedelta(hours=168)  # 扩大到 7 天
        result = await db.execute(
            select(Match).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.match_date >= now,
                Match.match_date <= cutoff,
            )
        )
        matches = result.scalars().all()

    if not matches:
        return []  # 无比赛，不调 GDELT

    keywords: set[str] = set()
    for match in matches[:20]:  # 最多 20 场比赛
        home_team = await db.get(Team, match.home_team_id)
        away_team = await db.get(Team, match.away_team_id)
        if not home_team or not away_team:
            continue

        home_name = home_team.name
        away_name = away_team.name

        keywords.add(f'"{home_name}" "{away_name}" preview')
        keywords.add(f'"{home_name}" injury')
        keywords.add(f'"{away_name}" injury')
        keywords.add(f'"{home_name}" lineup')
        keywords.add(f'"{away_name}" lineup')

    return list(keywords)[:20]


class NewsIngestService:
    SPORTS_TERMS = ("world cup", "fifa", "football", "soccer", "世界杯")

    def __init__(self) -> None:
        self.team_resolver = TeamResolver()

    async def fetch_event_registry(self, keywords: list[str] | None = None, hours_back: int = 24) -> list[dict[str, Any]]:
        if not settings.event_registry_api_key:
            logger.warning("EVENT_REGISTRY_API_KEY missing, skip Event Registry fetch")
            return []
        if not keywords:
            return []
        query_keywords = keywords
        payload = {
            "apiKey": settings.event_registry_api_key,
            "keyword": query_keywords,
            "lang": ["eng", "zho"],
            "dateStart": (utc_now() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "articlesSortBy": "date",
            "isDuplicateFilter": "skipDuplicates",
            "resultType": "articles",
            "articlesCount": 50,
            "includeArticleBody": True,
        }
        async with httpx.AsyncClient() as client:
            data = await fetch_json(
                client,
                "https://eventregistry.org/api/v1/article/getArticles",
                params=payload,
            )
        articles = data.get("articles", {}).get("results", [])
        return [
            {
                "source_name": article.get("source", {}).get("title"),
                "source_url": article.get("url"),
                "title": article.get("title"),
                "content": article.get("body") or article.get("summary") or "",
                "language": article.get("lang"),
                "published_at": article.get("dateTimePub") or article.get("dateTime"),
                "fetched_at": utc_now().isoformat(),
            }
            for article in articles
            if article.get("url") and article.get("title")
        ]

    async def fetch_gdelt(self, keywords: list[str] | None = None, hours_back: int = 6) -> list[dict[str, Any]]:
        if not keywords:
            return []
        query_keywords = keywords
        query = "(" + " OR ".join(f"({keyword})" for keyword in query_keywords) + ") AND (football OR soccer OR fifa)"
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": 50,
            "timespan": f"{hours_back}h",
            "sort": "DateDesc",
        }
        async with httpx.AsyncClient() as client:
            data = await fetch_json(client, settings.gdelt_base_url, params=params)
        articles = data.get("articles", [])
        normalized_articles: list[dict[str, Any]] = []
        for article in articles:
            title = str(article.get("title") or "")
            snippet = str(article.get("snippet") or "").strip()
            # seendate is a timestamp (e.g. "20260512T173000Z") — NEVER use as content
            # Short snippets (<80 chars) are discarded at collection time
            if not snippet or len(snippet) < 80:
                continue
            content = snippet
            combined_text = f"{title} {content}".lower()
            if not any(term in combined_text for term in self.SPORTS_TERMS):
                continue
            normalized_articles.append(
                {
                    "source_name": article.get("sourcecountry") or article.get("domain"),
                    "source_url": article.get("url"),
                    "title": title,
                    "content": content,
                    "language": article.get("language"),
                    "published_at": article.get("seendate"),
                    "fetched_at": utc_now().isoformat(),
                }
            )
        return normalized_articles

    async def fetch_rss_feeds(self) -> list[dict[str, Any]]:
        config_path = Path(__file__).resolve().parent.parent / "configs" / "rss_sources.yaml"
        if not config_path.exists():
            return []
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        feed_urls = config.get("feeds", [])
        articles: list[dict[str, Any]] = []

        for feed_url in feed_urls:
            parsed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in parsed.entries[:20]:
                articles.append(
                    {
                        "source_name": parsed.feed.get("title"),
                        "source_url": entry.get("link"),
                        "title": entry.get("title"),
                        "content": entry.get("summary", ""),
                        "language": parsed.feed.get("language"),
                        "published_at": entry.get("published"),
                        "fetched_at": utc_now().isoformat(),
                    }
                )
        return articles

    async def deduplicate_and_store(self, articles: list[dict[str, Any]], db: AsyncSession) -> int:
        inserted = 0
        for article in articles:
            source_url = article.get("source_url")
            title = article.get("title")
            content = article.get("content")
            if not source_url or not title or not content:
                continue
            external_id = sha256_text(source_url)
            result = await db.execute(select(NewsArticle).where(NewsArticle.external_id == external_id))
            if result.scalar_one_or_none() is not None:
                continue
            db.add(
                NewsArticle(
                    external_id=external_id,
                    source_name=article.get("source_name"),
                    source_url=source_url,
                    title=title,
                    content=content,
                    language=article.get("language"),
                    published_at=self._parse_datetime(article.get("published_at")),
                    fetched_at=self._parse_datetime(article.get("fetched_at")) or utc_now(),
                    is_processed=False,
                )
            )
            inserted += 1
        await db.commit()
        return inserted

    async def collect_latest_articles(
        self,
        db: AsyncSession,
        *,
        keywords: list[str] | None = None,
        hours_back: int = 24,
        include_rss: bool = True,
    ) -> dict[str, int]:
        query_keywords = keywords
        if query_keywords is None:
            query_keywords = await build_match_keywords(db)
            logger.info(
                "match keywords: %d, upcoming matches in window",
                len(query_keywords),
            )
        event_registry_articles = await self.fetch_event_registry(query_keywords, hours_back=hours_back) if query_keywords else []
        gdelt_articles = await self.fetch_gdelt(query_keywords, hours_back=min(hours_back, 24)) if query_keywords else []
        rss_articles = await self.fetch_rss_feeds() if include_rss else []
        inserted = await self.deduplicate_and_store(
            [*event_registry_articles, *gdelt_articles, *rss_articles],
            db,
        )
        return {
            "event_registry": len(event_registry_articles),
            "gdelt": len(gdelt_articles),
            "rss": len(rss_articles),
            "inserted": inserted,
        }

    async def calculate_source_reliability(self, source_url: str, db: AsyncSession) -> float:
        return await self.team_resolver.lookup_source_reliability(source_url, db)

    async def create_manual_signal(self, payload: ManualSignalCreateRequest, db: AsyncSession):
        article = NewsArticle(
            external_id=sha256_text(f"{payload.source_url}:{payload.article_title}:{utc_now().isoformat()}"),
            source_name=payload.source_name,
            source_url=payload.source_url,
            title=payload.article_title,
            content=payload.article_content or payload.summary_zh,
            language=payload.language,
            published_at=utc_now(),
            fetched_at=utc_now(),
            is_processed=True,
        )
        db.add(article)
        await db.flush()

        team = await self.team_resolver.resolve_team(payload.team_name, db) if payload.team_name else None
        match = None
        if payload.match_id:
            match = await db.get(Match, payload.match_id)
        elif team is not None:
            result = await db.execute(
                select(Match)
                .where(
                    ((Match.home_team_id == team.id) | (Match.away_team_id == team.id)),
                    Match.match_date >= utc_now() - timedelta(days=3),
                    Match.match_date <= utc_now() + timedelta(days=14),
                )
                .order_by(Match.match_date.asc())
            )
            match = result.scalars().first()

        signal = NewsSignal(
            article_id=article.id,
            match_id=match.id if match else payload.match_id,
            team_id=team.id if team else None,
            signal_type=SignalType(payload.signal_type),
            impact_direction=ImpactDirection(payload.impact_direction),
            confidence=payload.confidence,
            key_players=payload.key_players,
            summary_zh=payload.summary_zh,
            player_name=payload.key_players[0] if payload.key_players else None,
            claim=payload.summary_zh,
            evidence_snippet=(payload.article_content or payload.summary_zh)[:300],
            source_reliability=payload.source_reliability,
            review_status=ReviewStatus.APPROVED if payload.enters_model else ReviewStatus.PENDING,
            review_notes=payload.review_notes,
            reviewed_by=payload.reviewed_by if payload.enters_model else None,
            reviewed_at=utc_now() if payload.enters_model else None,
            enters_model=payload.enters_model,
        )
        db.add(signal)
        await db.commit()
        await db.refresh(signal)
        return signal.id

    @staticmethod
    def _parse_datetime(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                from dateutil import parser

                return parser.parse(value)
            except Exception:
                return None
