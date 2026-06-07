"""Periodic data-refresh logic called by Celery Beat tasks.

Two jobs:
  refresh_news      – scrape recent HKFP headlines, embed new ones, upsert to Qdrant
  refresh_datasets  – re-sync HK open-data catalog to Qdrant (incremental)

Both are idempotent: deterministic UUID5 IDs mean re-runs skip already-embedded records.
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import date, timedelta
from functools import lru_cache

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

log = logging.getLogger(__name__)

# ── shared constants ───────────────────────────────────────────────────────
_OPENAI_EMBED_MODEL = "text-embedding-3-small"
_VECTOR_DIM = 1536
_BATCH_SIZE = 128
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# ── lazy singletons ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _openai() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


@lru_cache(maxsize=1)
def _qdrant() -> QdrantClient:
    return QdrantClient(
        url=os.environ["QDRANT_HOST"],
        api_key=os.environ["QDRANT_API_KEY"],
    )


# ── Qdrant helpers ─────────────────────────────────────────────────────────

def _ensure_collection(name: str) -> None:
    client = _qdrant()
    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        info = client.get_collection(name)
        existing_dim = info.config.params.vectors.size
        if existing_dim != _VECTOR_DIM:
            log.info(
                "[qdrant] collection '%s' has wrong vector dim (%d != %d), recreating",
                name, existing_dim, _VECTOR_DIM,
            )
            client.delete_collection(name)
        else:
            return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=_VECTOR_DIM, distance=Distance.COSINE),
    )
    log.info("[qdrant] created collection '%s'", name)


def _existing_ids(collection: str, source: str) -> set[str]:
    client = _qdrant()
    source_filter = Filter(
        must=[FieldCondition(key="source", match=MatchValue(value=source))]
    )
    ids: set[str] = set()
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection,
            scroll_filter=source_filter,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        for pt in batch:
            ids.add(str(pt.id))
        if offset is None:
            break
    return ids


def _upsert_batch(collection: str, items: list[dict]) -> None:
    texts = [item["text"] for item in items]
    resp = _openai().embeddings.create(input=texts, model=_OPENAI_EMBED_MODEL)
    vectors = [item.embedding for item in resp.data]
    points = [
        PointStruct(id=item["id"], vector=vec, payload=item["payload"])
        for item, vec in zip(items, vectors)
    ]
    _qdrant().upsert(collection_name=collection, points=points)


# ── news refresh ───────────────────────────────────────────────────────────

_HKFP_ARCHIVE = "https://hongkongfp.com/archive/"
_UA = "Mozilla/5.0 (compatible; CityPilot-refresh/1.0)"
_DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")
_NEWS_COLLECTION = "hk_news_articles"
_NEWS_SOURCE = "hkfp_news"
# Only look back this many days on each refresh run.
_REFRESH_LOOKBACK_DAYS = 14


def _page_url(n: int) -> str:
    return _HKFP_ARCHIVE if n == 1 else f"{_HKFP_ARCHIVE}page/{n}/"


def _fetch_html(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
            if r.status_code == 404:
                return ""
            if r.status_code == 429:
                time.sleep(15 * (2 ** attempt))
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return ""


def _parse_articles(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for art in soup.select("article"):
        title_el = art.select_one(".entry-title a, h2 a, h3 a, .post-title a")
        date_el = art.select_one("time[datetime], time")
        auth_el = art.select_one("[rel='author'], .author a, .byline a, .post-author a")
        if not title_el:
            continue
        raw = (date_el.get("datetime") or date_el.get_text(strip=True)) if date_el else ""
        results.append({
            "title": title_el.get_text(strip=True),
            "url": title_el.get("href", ""),
            "date": raw[:10] if raw else "",
            "author": auth_el.get_text(strip=True) if auth_el else "",
        })
    return results


def _article_date(art: dict) -> date | None:
    m = _DATE_RE.search(art.get("url", ""))
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    try:
        return date.fromisoformat(art["date"]) if art.get("date") else None
    except ValueError:
        return None


def refresh_news() -> int:
    """Scrape the most recent HKFP pages and upsert any new articles."""
    cutoff = date.today() - timedelta(days=_REFRESH_LOOKBACK_DAYS)
    _ensure_collection(_NEWS_COLLECTION)
    existing = _existing_ids(_NEWS_COLLECTION, _NEWS_SOURCE)

    articles: list[dict] = []
    for page_num in range(1, 20):
        html = _fetch_html(_page_url(page_num))
        if not html:
            break
        page_arts = _parse_articles(html)
        exhausted = False
        for art in page_arts:
            art_date = _article_date(art)
            if art_date and art_date < cutoff:
                exhausted = True
                break
            articles.append(art)
        if exhausted:
            break
        time.sleep(0.5)

    new_items = []
    for art in articles:
        if not art.get("url", "").startswith("http"):
            continue
        m = _DATE_RE.search(art["url"])
        canonical_date = (
            f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else art.get("date", "")
        )
        record_id = str(uuid.uuid5(_NS, art["url"]))
        if record_id in existing:
            continue
        text = " | ".join(p for p in (art["title"], canonical_date, art.get("author", "")) if p)
        new_items.append({
            "id": record_id,
            "text": text,
            "payload": {
                "source": _NEWS_SOURCE,
                "title": art["title"],
                "url": art["url"],
                "date": canonical_date,
                "author": art.get("author", ""),
            },
        })

    for i in range(0, len(new_items), _BATCH_SIZE):
        _upsert_batch(_NEWS_COLLECTION, new_items[i : i + _BATCH_SIZE])

    log.info("[refresh_news] upserted %d new articles", len(new_items))
    return len(new_items)


# ── dataset refresh ────────────────────────────────────────────────────────

_DATASETS_URL = (
    "https://resource.data.one.gov.hk/opendata/open-data-list/"
    "open-data-dataset-list-en.json"
)
_DATASETS_COLLECTION = "hk_open_datasets"
_DATASETS_SOURCE = "hk_data_gov"
_HK_PAGE_BASE = "https://data.gov.hk/en-data/dataset"


def refresh_datasets() -> int:
    """Fetch the full HK open-data list and embed any new records."""
    _ensure_collection(_DATASETS_COLLECTION)
    existing = _existing_ids(_DATASETS_COLLECTION, _DATASETS_SOURCE)

    resp = requests.get(_DATASETS_URL, timeout=30)
    resp.raise_for_status()
    records = json.loads(resp.content.decode("utf-8-sig"))["Data"]

    new_items = []
    for r in records:
        record_id = str(uuid.uuid5(_NS, f"{r['Dataset ID']}::{r.get('Resource Name', '')}"))
        if record_id in existing:
            continue
        text = (
            f"{r['Dataset Name']} | "
            f"{r.get('Category', '')} | "
            f"{r.get('Data Provider', '')} | "
            f"{r.get('Resource Name', '')}"
        )
        new_items.append({
            "id": record_id,
            "text": text,
            "payload": {
                "source": _DATASETS_SOURCE,
                "dataset_id": r["Dataset ID"],
                "dataset_name": r["Dataset Name"],
                "resource_name": r.get("Resource Name", ""),
                "category": r.get("Category", ""),
                "data_provider": r.get("Data Provider", ""),
                "data_format": r.get("Data Format", ""),
            },
        })

    for i in range(0, len(new_items), _BATCH_SIZE):
        _upsert_batch(_DATASETS_COLLECTION, new_items[i : i + _BATCH_SIZE])

    log.info("[refresh_datasets] upserted %d new dataset records", len(new_items))
    return len(new_items)
