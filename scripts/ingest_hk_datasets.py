"""Fetch Hong Kong open data list, enrich with CKAN metadata, embed, upsert to Qdrant.

For each unique dataset ID in the bulk list, calls the CKAN package_show endpoint
to fetch richer metadata (notes/description, tags, update_frequency, per-resource
descriptions). The enriched text is embedded with OpenAI text-embedding-3-small.

Skips records whose deterministic UUID is already present in the collection,
so the script is safe to re-run incrementally.

Usage (from any directory):
    uv run scripts/ingest_hk_datasets.py

Requires QDRANT_HOST, QDRANT_API_KEY, and OPENAI_API_KEY in the project-root .env file.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "qdrant-client>=1.9.0",
#   "openai>=1.0.0",
#   "httpx>=0.27.0",
#   "requests>=2.32.0",
#   "python-dotenv>=1.0.0",
# ]
# ///
"""

import asyncio
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path

import httpx
import requests
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# ---------------------------------------------------------------------------
BULK_LIST_URL = (
    "https://resource.data.one.gov.hk/opendata/open-data-list/"
    "open-data-dataset-list-en.json"
)
CKAN_BASE = "https://data.gov.hk/en-data/api/3/action"
COLLECTION = "hk_open_datasets"
OPENAI_EMBED_MODEL = "text-embedding-3-small"
VECTOR_DIM = 1536
BATCH_SIZE = 50
CKAN_CONCURRENCY = 20  # parallel package_show requests
# Namespace for deterministic UUID5 IDs — fixed so re-runs produce same IDs.
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
# ---------------------------------------------------------------------------


def _record_id(dataset_id: str, resource_name: str) -> str:
    return str(uuid.uuid5(_NS, f"{dataset_id}::{resource_name}"))


def _record_text(r: dict, pkg: dict) -> str:
    """Build a rich embedding string from bulk-list row + CKAN package metadata."""
    tags = ", ".join(t["name"] for t in pkg.get("tags", []) if t.get("name"))
    resource_desc = _resource_description(pkg, r.get("Resource Name", ""))
    parts = [
        r["Dataset Name"],
        pkg.get("notes", ""),
        r.get("Category", ""),
        r.get("Data Provider", ""),
        pkg.get("update_frequency", ""),
        tags,
        r.get("Resource Name", ""),
        resource_desc,
    ]
    return " | ".join(p.strip() for p in parts if p.strip())


def _resource_description(pkg: dict, resource_name: str) -> str:
    """Find the CKAN resource matching resource_name and return its description."""
    name = resource_name.strip().lower()
    for res in pkg.get("resources", []):
        if res.get("name", "").strip().lower() == name:
            return res.get("description", "")
    return ""


# ── CKAN enrichment ────────────────────────────────────────────────────────

async def _fetch_package(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    dataset_id: str,
) -> tuple[str, dict]:
    """Return (dataset_id, package_dict); empty dict on any error."""
    async with sem:
        try:
            r = await client.get(
                f"{CKAN_BASE}/package_show",
                params={"id": dataset_id},
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    return dataset_id, data["result"]
        except Exception:
            pass
        return dataset_id, {}


async def fetch_all_packages(dataset_ids: list[str]) -> dict[str, dict]:
    """Concurrently fetch CKAN package_show for all dataset IDs."""
    sem = asyncio.Semaphore(CKAN_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_package(client, sem, ds_id) for ds_id in dataset_ids]
        )
    return dict(results)


# ── Qdrant helpers ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _openai_client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _embed(texts: list[str]) -> list[list[float]]:
    resp = _openai_client().embeddings.create(input=texts, model=OPENAI_EMBED_MODEL)
    return [item.embedding for item in resp.data]


def ensure_collection(client: QdrantClient) -> None:
    names = {c.name for c in client.get_collections().collections}
    if COLLECTION in names:
        info = client.get_collection(COLLECTION)
        existing_dim = info.config.params.vectors.size
        if existing_dim != VECTOR_DIM:
            print(
                f"[qdrant] collection '{COLLECTION}' has wrong vector dim "
                f"({existing_dim} != {VECTOR_DIM}), deleting and recreating..."
            )
            client.delete_collection(COLLECTION)
        else:
            print(f"[qdrant] collection '{COLLECTION}' exists ({info.points_count} points)")
            return
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"[qdrant] created collection '{COLLECTION}'")


def get_existing_ids(client: QdrantClient) -> set[str]:
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


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    qdrant_url = os.environ["QDRANT_HOST"]
    qdrant_key = os.environ["QDRANT_API_KEY"]

    client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
    print(f"[qdrant] connected to {qdrant_url}")

    ensure_collection(client)

    print("[fetch] downloading HK open data bulk list...")
    resp = requests.get(BULK_LIST_URL, timeout=30)
    resp.raise_for_status()
    records = json.loads(resp.content.decode("utf-8-sig"))["Data"]
    print(f"[fetch] {len(records)} resource rows")

    dataset_ids = list({r["Dataset ID"] for r in records})
    print(f"[ckan] fetching package_show for {len(dataset_ids)} unique datasets "
          f"({CKAN_CONCURRENCY} concurrent)...")
    packages = asyncio.run(fetch_all_packages(dataset_ids))
    ok = sum(1 for p in packages.values() if p)
    print(f"[ckan] enriched {ok}/{len(dataset_ids)} datasets (rest used empty fallback)")

    all_items = [
        {
            "id": _record_id(r["Dataset ID"], r.get("Resource Name", "")),
            "text": _record_text(r, packages.get(r["Dataset ID"], {})),
            "payload": {
                "source": "hk_data_gov",
                "dataset_id": r["Dataset ID"],
                "dataset_name": r["Dataset Name"],
                "resource_name": r.get("Resource Name", ""),
                "category": r.get("Category", ""),
                "data_provider": r.get("Data Provider", ""),
                "data_format": r.get("Data Format", ""),
                "notes": packages.get(r["Dataset ID"], {}).get("notes", ""),
                "update_frequency": packages.get(r["Dataset ID"], {}).get("update_frequency", ""),
                "tags": [t["name"] for t in packages.get(r["Dataset ID"], {}).get("tags", []) if t.get("name")],
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

    print(f"[openai] embedding {len(new_items)} records with '{OPENAI_EMBED_MODEL}'...")
    total = len(new_items)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = new_items[batch_start : batch_start + BATCH_SIZE]
        vectors = _embed([item["text"] for item in batch])
        points = [
            PointStruct(id=item["id"], vector=vec, payload=item["payload"])
            for item, vec in zip(batch, vectors)
        ]
        for attempt in range(3):
            try:
                client.upsert(collection_name=COLLECTION, points=points)
                break
            except Exception:
                if attempt == 2:
                    raise
                import time; time.sleep(2 ** attempt)
        done = min(batch_start + BATCH_SIZE, total)
        print(f"  upserted {done}/{total}", end="\r", flush=True)

    print(f"\n[done] embedded and upserted {total} new records.")


if __name__ == "__main__":
    main()
