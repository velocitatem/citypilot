"""Fetch Hong Kong open data list, embed dataset names, upsert to Qdrant.

Skips records whose deterministic UUID is already present in the collection,
so the script is safe to re-run incrementally.

Usage (from any directory):
    uv run scripts/ingest_hk_datasets.py

Requires QDRANT_HOST and QDRANT_API_KEY in the project-root .env file.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "qdrant-client>=1.9.0",
#   "sentence-transformers>=3.0.0",
#   "requests>=2.32.0",
#   "python-dotenv>=1.0.0",
# ]
# ///
"""

import json
import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
DATA_URL = (
    "https://resource.data.one.gov.hk/opendata/open-data-list/"
    "open-data-dataset-list-en.json"
)
COLLECTION = "hk_open_datasets"
MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM = 384
BATCH_SIZE = 128
# Namespace for deterministic UUID5 IDs — fixed so re-runs produce same IDs.
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
# ---------------------------------------------------------------------------


def _record_id(dataset_id: str, resource_name: str) -> str:
    return str(uuid.uuid5(_NS, f"{dataset_id}::{resource_name}"))


def _record_text(r: dict) -> str:
    return (
        f"{r['Dataset Name']} | "
        f"{r.get('Category', '')} | "
        f"{r.get('Data Provider', '')} | "
        f"{r.get('Resource Name', '')}"
    )


def fetch_records() -> list[dict]:
    resp = requests.get(DATA_URL, timeout=30)
    resp.raise_for_status()
    data = json.loads(resp.content.decode("utf-8-sig"))
    return data["Data"]


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
    """Scroll the full collection and return all existing point IDs."""
    ids: set[str] = set()
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION,
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
    # Load .env from project root (two levels up from scripts/)
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    qdrant_url = os.environ["QDRANT_HOST"]
    qdrant_key = os.environ["QDRANT_API_KEY"]

    client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
    print(f"[qdrant] connected to {qdrant_url}")

    ensure_collection(client)

    print("[fetch] downloading HK open data list...")
    records = fetch_records()
    print(f"[fetch] {len(records)} records")

    all_items = [
        {
            "id": _record_id(r["Dataset ID"], r.get("Resource Name", "")),
            "text": _record_text(r),
            "payload": {
                "source": "hk_data_gov",
                "dataset_id": r["Dataset ID"],
                "dataset_name": r["Dataset Name"],
                "resource_name": r.get("Resource Name", ""),
                "category": r.get("Category", ""),
                "data_provider": r.get("Data Provider", ""),
                "data_format": r.get("Data Format", ""),
            },
        }
        for r in records
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
