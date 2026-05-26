from __future__ import annotations

import asyncio
import hashlib
import math
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging import get_logger
from app.models import NewsArticle, NewsSignal

settings = get_settings()
logger = get_logger(__name__)

EMBEDDING_DIMENSIONS = 1536
LOCAL_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as exc:  # pragma: no cover - depends on optional runtime install
        logger.warning("sentence-transformers unavailable, using deterministic hash embeddings: %s", exc)
        return None


class EmbeddingService:
    """
    支持本地和 API 两种 embedding 模式。
    """

    async def embed_text(self, text: str) -> list[float]:
        cleaned = (text or "").strip()
        if not cleaned:
            return [0.0] * EMBEDDING_DIMENSIONS
        if settings.embedding_mode == "api":
            try:
                return await self._embed_with_api(cleaned)
            except Exception as exc:
                logger.warning("API embeddings failed, falling back to local mode: %s", exc)
        return await self._embed_locally(cleaned)

    async def embed_article(self, article_id: UUID, db: AsyncSession) -> bool:
        article = await db.get(NewsArticle, article_id)
        if article is None or article.embedding is not None:
            return False
        article.embedding = await self.embed_text(f"{article.title}\n\n{article.content[:4000]}")
        article.embedding_model = self._embedding_model_name()
        await db.commit()
        return True

    async def batch_embed_articles(self, db: AsyncSession, batch_size: int = 20) -> int:
        result = await db.execute(
            select(NewsArticle)
            .where(NewsArticle.embedding.is_(None))
            .order_by(NewsArticle.created_at.asc())
            .limit(max(1, batch_size))
        )
        articles = result.scalars().all()
        processed = 0
        for article in articles:
            article.embedding = await self.embed_text(f"{article.title}\n\n{article.content[:4000]}")
            article.embedding_model = self._embedding_model_name()
            processed += 1
        if processed:
            await db.commit()
        return processed

    async def search_similar(
        self,
        query_text: str,
        match_id: UUID,
        db: AsyncSession,
        top_k: int = 5,
        min_relevance: float = 0.6,
    ) -> list[dict[str, Any]]:
        query_embedding = await self.embed_text(query_text)
        dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
        dialect_name = getattr(dialect_name, "name", "")
        if dialect_name == "postgresql":
            postgres_results = await self._search_similar_postgres(
                query_text=query_text,
                query_embedding=query_embedding,
                match_id=match_id,
                db=db,
                top_k=top_k,
                min_relevance=min_relevance,
            )
            if postgres_results:
                return postgres_results

        result = await db.execute(
            select(NewsArticle)
            .join(NewsSignal, NewsSignal.article_id == NewsArticle.id)
            .where(
                NewsSignal.match_id == match_id,
                NewsArticle.embedding.is_not(None),
            )
            .order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.created_at.desc())
            .distinct()
        )
        articles = result.scalars().all()
        scored: list[dict[str, Any]] = []
        for article in articles:
            if not article.embedding:
                continue
            relevance = self._cosine_similarity(query_embedding, article.embedding)
            if relevance < min_relevance:
                continue
            scored.append(
                {
                    "article_id": article.id,
                    "title": article.title,
                    "snippet": self._best_snippet(query_text, article.content),
                    "relevance_score": round(relevance, 4),
                    "source_name": article.source_name,
                    "source_url": article.source_url,
                    "published_at": article.published_at,
                }
            )
        scored.sort(key=lambda item: item["relevance_score"], reverse=True)
        return scored[:top_k]

    async def _search_similar_postgres(
        self,
        query_text: str,
        query_embedding: list[float],
        match_id: UUID,
        db: AsyncSession,
        top_k: int,
        min_relevance: float,
    ) -> list[dict[str, Any]]:
        try:
            distance_expr = NewsArticle.embedding.cosine_distance(query_embedding)  # type: ignore[attr-defined]
        except Exception:
            return []

        result = await db.execute(
            select(NewsArticle, distance_expr.label("distance"))
            .join(NewsSignal, NewsSignal.article_id == NewsArticle.id)
            .where(
                NewsSignal.match_id == match_id,
                NewsArticle.embedding.is_not(None),
            )
            .order_by(distance_expr.asc(), NewsArticle.published_at.desc().nullslast(), NewsArticle.created_at.desc())
            .limit(max(top_k * 8, 20))
        )
        deduped: list[dict[str, Any]] = []
        seen_article_ids: set[UUID] = set()
        for article, distance in result.all():
            if article.id in seen_article_ids:
                continue
            seen_article_ids.add(article.id)
            relevance = float(np.clip(1.0 - float(distance or 1.0), 0.0, 1.0))
            if relevance < min_relevance:
                continue
            deduped.append(
                {
                    "article_id": article.id,
                    "title": article.title,
                    "snippet": self._best_snippet(query_text, article.content),
                    "relevance_score": round(relevance, 4),
                    "source_name": article.source_name,
                    "source_url": article.source_url,
                    "published_at": article.published_at,
                }
            )
            if len(deduped) >= top_k:
                break
        return deduped

    async def _embed_with_api(self, text: str) -> list[float]:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        base_url = settings.llm_base_url or self._default_provider_base_url()
        payload = {
            "model": settings.llm_model,
            "input": text,
        }
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        vector = data["data"][0]["embedding"]
        return self._prepare_embedding(vector)

    async def _embed_locally(self, text: str) -> list[float]:
        model = _load_sentence_transformer()
        if model is not None:
            vector = await asyncio.to_thread(model.encode, text, normalize_embeddings=True)
            return self._prepare_embedding(vector.tolist() if hasattr(vector, "tolist") else list(vector))
        return self._hash_embedding(text)

    def _prepare_embedding(self, vector: list[float]) -> list[float]:
        normalized = [float(value) for value in vector[:EMBEDDING_DIMENSIONS]]
        if len(normalized) < EMBEDDING_DIMENSIONS:
            normalized.extend([0.0] * (EMBEDDING_DIMENSIONS - len(normalized)))
        norm = math.sqrt(sum(value * value for value in normalized)) or 1.0
        return [value / norm for value in normalized]

    def _hash_embedding(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(EMBEDDING_DIMENSIONS)]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        left_vec = np.asarray(left, dtype=float)
        right_vec = np.asarray(right[: len(left)], dtype=float)
        denominator = float(np.linalg.norm(left_vec) * np.linalg.norm(right_vec))
        if denominator <= 0:
            return 0.0
        return float(np.clip(np.dot(left_vec, right_vec) / denominator, -1.0, 1.0))

    def _best_snippet(self, query_text: str, content: str, limit: int = 220) -> str:
        content = (content or "").strip().replace("\n", " ")
        if not content:
            return ""
        query_terms = [term for term in query_text.split() if len(term) > 2]
        lower_content = content.lower()
        for term in query_terms:
            position = lower_content.find(term.lower())
            if position >= 0:
                start = max(0, position - 60)
                end = min(len(content), position + limit)
                return content[start:end].strip()
        return content[:limit].strip()

    def _default_provider_base_url(self) -> str:
        if settings.llm_provider == "deepseek":
            return "https://api.deepseek.com/v1"
        if settings.llm_provider == "zhipu":
            return "https://open.bigmodel.cn/api/paas/v4"
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def _embedding_model_name(self) -> str:
        return settings.llm_model if settings.embedding_mode == "api" else LOCAL_MODEL_NAME
