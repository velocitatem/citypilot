"""Embed HKFP news headlines and upsert to Qdrant.

Reads data/hk_hkfp_headlines.csv, canonically derives the article date from
the URL path (/YYYY/MM/DD/), embeds each title+date+author text, and upserts
into the `hk_news_articles` Qdrant collection.

Points are tagged source="hkfp_news" so retrieval queries must filter by
source to avoid mixing news results with HK open-data dataset records
(source="hk_data_gov" in the `hk_open_datasets` collection).

Skips records whose deterministic UUID5 is already present — safe to re-run.

Usage (from project root):
    uv run scripts/ingest_hkfp_articles.py

Requires QDRANT_HOST and QDRANT_API_KEY in the project-root .env file.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "qdrant-client>=1.9.0",
#   "sentence-transformers>=3.0.0",
#   "pandas>=2.0.0",
#   "python-dotenv>=1.0.0",
# ]
# ///
"""

import os
import re
import uuid
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
CSV_PATH = Path("data/hk_hkfp_headlines.csv")
COLLECTION = "hk_news_articles"
SOURCE = "hkfp_news"
MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM = 384
BATCH_SIZE = 128
# Fixed namespace — deterministic IDs so re-runs are idempotent.
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
_DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")
# ---------------------------------------------------------------------------


def _extract_date(url: str) -> str:
    """Pull YYYY-MM-DD from the URL path (canonical source of truth)."""
    m = _DATE_RE.search(url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _record_id(url: str) -> str:
    return str(uuid.uuid5(_NS, url))


def _record_text(title: str, date: str, author: str) -> str:
    parts = [p for p in (title, date, author) if p]
    return " | ".join(parts)


def load_and_clean(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    # Canonically extract date from URL, fall back to existing date column.
    df["date"] = df["url"].map(_extract_date).where(
        df["url"].map(_extract_date) != "", df["date"]
    )
    df = df.drop_duplicates(subset=["url"])
    df = df[df["url"].str.startswith("http")]  # drop any malformed rows
    print(f"[csv] {len(df)} unique articles after cleaning")
    return df.reset_index(drop=True)


def ensure_collection(client: QdrantClient) -> None:
    names = {c.name for c in client.get_collections().collections}
    if COLLECTION not in names:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        print(f"[qdrant] created collection '{COLLECTION}'")
    else:
        info = client.get_collection(COLLECTION)
        print(
            f"[qdrant] collection '{COLLECTION}' exists "
            f"({info.points_count} points)"
        )


def get_existing_ids(client: QdrantClient) -> set[str]:
    """Scroll only hkfp_news points to get existing IDs."""
    ids: set[str] = set()
    offset = None
    source_filter = Filter(
        must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))]
    )
    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION,
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


def main() -> None:
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    qdrant_url = os.environ["QDRANT_HOST"]
    qdrant_key = os.environ["QDRANT_API_KEY"]

    client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
    print(f"[qdrant] connected to {qdrant_url}")

    ensure_collection(client)

    df = load_and_clean(project_root / CSV_PATH)

    all_items = [
        {
            "id": _record_id(row["url"]),
            "text": _record_text(row["title"], row["date"], row["author"]),
            "payload": {
                "source": SOURCE,
                "title": row["title"],
                "url": row["url"],
                "date": row["date"],
                "author": row["author"],
            },
        }
        for _, row in df.iterrows()
    ]

    print("[qdrant] checking for already-embedded records...")
    existing_ids = get_existing_ids(client)
    new_items = [item for item in all_items if item["id"] not in existing_ids]
    print(f"  already embedded : {len(existing_ids)}")
    print(f"  new to embed     : {len(new_items)}")

    if not new_items:
        print("[done] nothing new to embed.")
        return

    print(f"[model] loading '{MODEL_NAME}'...")
    model = SentenceTransformer(MODEL_NAME)

    total = len(new_items)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = new_items[batch_start : batch_start + BATCH_SIZE]
        vectors = model.encode(
            [item["text"] for item in batch],
            show_progress_bar=False,
        ).tolist()
        points = [
            PointStruct(id=item["id"], vector=vec, payload=item["payload"])
            for item, vec in zip(batch, vectors)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        done = min(batch_start + BATCH_SIZE, total)
        print(f"  upserted {done}/{total}", end="\r", flush=True)

    print(f"\n[done] embedded and upserted {total} new records.")


if __name__ == "__main__":
    main()
