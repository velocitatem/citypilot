"""HKFP news article tools.

search_news       – semantic search over the hk_news_articles Qdrant collection
get_recent_news   – fetch the N most recent articles, optionally filtered by date
"""

import os
from functools import lru_cache

from langchain_core.tools import tool
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, OrderBy, Range
from sentence_transformers import SentenceTransformer

from context import RunContext

COLLECTION = "hk_news_articles"
SOURCE = "hkfp_news"
MODEL_NAME = "all-MiniLM-L6-v2"

_SOURCE_FILTER = Filter(
    must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))]
)


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def _qdrant() -> QdrantClient:
    return QdrantClient(
        url=os.environ["QDRANT_HOST"],
        api_key=os.environ["QDRANT_API_KEY"],
    )


def news_tools(ctx: RunContext) -> list:  # noqa: ARG001
    @tool
    def search_news(query: str, top_k: int = 10) -> list[dict]:
        """Semantic search over Hong Kong Free Press news headlines in Qdrant.

        Returns up to `top_k` articles ranked by relevance to a natural-language
        query. Each result includes title, url, date, author, and score.
        Always filters to source='hkfp_news' so dataset records are never mixed in.
        """
        vec = _model().encode(query).tolist()
        response = _qdrant().query_points(
            collection_name=COLLECTION,
            query=vec,
            query_filter=_SOURCE_FILTER,
            limit=top_k,
            with_payload=True,
        )
        return [
            {**(h.payload or {}), "score": round(h.score, 4)}
            for h in response.points
        ]

    @tool
    def get_recent_news(
        limit: int = 20,
        since: str = "",
        until: str = "",
    ) -> list[dict]:
        """Fetch the most recent HKFP news articles, optionally bounded by date.

        `since` / `until`: optional ISO date strings (YYYY-MM-DD) to filter the
        range. Omit both to get the latest `limit` articles.
        Returns a list of {title, url, date, author}.
        """
        conditions = [FieldCondition(key="source", match=MatchValue(value=SOURCE))]
        date_range: dict = {}
        if since:
            date_range["gte"] = since
        if until:
            date_range["lte"] = until
        if date_range:
            conditions.append(FieldCondition(key="date", range=Range(**date_range)))

        results, _ = _qdrant().scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(must=conditions),
            limit=limit,
            order_by=OrderBy(key="date", direction="desc"),
            with_payload=True,
            with_vectors=False,
        )
        return [pt.payload for pt in results if pt.payload]

    return [search_news, get_recent_news]
