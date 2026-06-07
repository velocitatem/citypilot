"""HKFP news article tools.

search_news       – semantic search over the hk_news_articles Qdrant collection
get_recent_news   – fetch the N most recent articles, optionally filtered by date
"""

import os
from functools import lru_cache

from langchain_core.tools import tool
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, OrderBy

from context import RunContext


def _tool_err(e: Exception) -> str:
    return f"[tool_error] {type(e).__name__}: {e}"

COLLECTION = "hk_news_articles"
SOURCE = "hkfp_news"
OPENAI_EMBED_MODEL = "text-embedding-3-small"

_SOURCE_FILTER = Filter(
    must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))]
)


@lru_cache(maxsize=1)
def _openai() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


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
        try:
            resp = _openai().embeddings.create(input=[query], model=OPENAI_EMBED_MODEL)
            vec = resp.data[0].embedding
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
        except Exception as e:
            return _tool_err(e)

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
        scroll_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))]
        )
        fetch_limit = limit * 10 if (since or until) else limit
        try:
            try:
                results, _ = _qdrant().scroll(
                    collection_name=COLLECTION,
                    scroll_filter=scroll_filter,
                    limit=fetch_limit,
                    order_by=OrderBy(key="date", direction="desc"),
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception:
                # date index is KEYWORD (no range index) — fall back to unordered scroll
                results, _ = _qdrant().scroll(
                    collection_name=COLLECTION,
                    scroll_filter=scroll_filter,
                    limit=max(fetch_limit, 500),
                    with_payload=True,
                    with_vectors=False,
                )
            records = [pt.payload for pt in results if pt.payload]
            records.sort(key=lambda r: r.get("date") or "", reverse=True)
            if since:
                records = [r for r in records if (r.get("date") or "") >= since]
            if until:
                records = [r for r in records if (r.get("date") or "") <= until]
            return records[:limit]
        except Exception as e:
            return _tool_err(e)

    return [search_news, get_recent_news]
