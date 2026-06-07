"""Delete the embedding collections from Qdrant so they can be re-created with
OpenAI text-embedding-3-small (1536 dims) on the next ingest run.

Usage (from project root):
    uv run scripts/reset_qdrant_collections.py

Requires QDRANT_HOST and QDRANT_API_KEY in the project-root .env file.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "qdrant-client>=1.9.0",
#   "python-dotenv>=1.0.0",
# ]
# ///
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

COLLECTIONS = ["hk_news_articles", "hk_open_datasets"]


def main() -> None:
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    client = QdrantClient(
        url=os.environ["QDRANT_HOST"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    print(f"[qdrant] connected to {os.environ['QDRANT_HOST']}")

    existing = {c.name for c in client.get_collections().collections}
    for name in COLLECTIONS:
        if name in existing:
            client.delete_collection(name)
            print(f"[qdrant] deleted collection '{name}'")
        else:
            print(f"[qdrant] collection '{name}' does not exist, skipping")

    print("[done] collections cleared — re-run the ingest scripts to repopulate.")


if __name__ == "__main__":
    main()
