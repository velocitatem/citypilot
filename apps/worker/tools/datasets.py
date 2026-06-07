"""Dataset discovery and retrieval tools.

search_datasets       – semantic search over Qdrant catalog (best for natural language)
browse_datasets       – keyword search via CKAN package_search
get_dataset_details   – resource list for a dataset via CKAN package_show
download_dataset_file – fetch a resource file via historical-archive or live URL
"""

import csv
import io
import json
import os
from datetime import date as _date, timedelta
from functools import lru_cache

import requests
from langchain_core.tools import tool
from openai import OpenAI
from qdrant_client import QdrantClient

from context import RunContext

# ── constants ──────────────────────────────────────────────────────────────
COLLECTION = "hk_open_datasets"
OPENAI_EMBED_MODEL = "text-embedding-3-small"
MAX_PREVIEW_ROWS = 200
MAX_TEXT_BYTES = 8_000

_HK_PAGE_BASE = "https://data.gov.hk/en-data/dataset"
_HK_CKAN_BASE = "https://data.gov.hk/en-data/api/3/action"
_HK_GET_FILE = "https://app.data.gov.hk/v1/historical-archive/get-file"
_HK_LIST_VER = "https://api.data.gov.hk/v1/historical-archive/list-file-versions"
_CKAN_TIMEOUT = 15
_HEADERS = {"User-Agent": "citypilot/1.0 (data.gov.hk research agent)"}


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


# ── CKAN helpers ───────────────────────────────────────────────────────────
def _ckan_get(action: str, params: dict) -> dict:
    resp = requests.get(f"{_HK_CKAN_BASE}/{action}", params=params, headers=_HEADERS, timeout=_CKAN_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"CKAN error: {data.get('error', 'unknown')}")
    return data["result"]


# ── download handler for HK data.gov ──────────────────────────────────────
def _hk_download_file(resource_url: str, date: str = "") -> str:
    """Tries the HK historical-archive API first; falls back to direct fetch."""
    yesterday = (_date.today() - timedelta(days=1)).strftime("%Y%m%d")
    target_date = date or yesterday

    if not date:
        try:
            ver_resp = requests.get(
                _HK_LIST_VER,
                params={"url": resource_url, "start": "20240101", "end": yesterday},
                headers=_HEADERS,
                timeout=15,
            )
            if ver_resp.ok:
                timestamps = ver_resp.json().get("timestamps", [])
                if timestamps:
                    target_date = sorted(timestamps)[-1]
        except Exception:
            pass

    archive_resp = requests.get(
        _HK_GET_FILE,
        params={"url": resource_url, "time": target_date},
        headers=_HEADERS,
        timeout=30,
    )
    if archive_resp.status_code == 200 and archive_resp.content:
        return _parse_response(archive_resp, resource_url)

    live_resp = requests.get(resource_url, headers=_HEADERS, timeout=30)
    live_resp.raise_for_status()
    return _parse_response(live_resp, resource_url)


def _parse_response(resp: requests.Response, url: str) -> str:
    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type or url.lower().endswith(".json"):
        data = resp.json()
        rows = data if isinstance(data, list) else [data]
        return json.dumps(rows[:MAX_PREVIEW_ROWS], indent=2)
    if "csv" in content_type or url.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        return json.dumps(rows[:MAX_PREVIEW_ROWS], indent=2)
    return resp.text[:MAX_TEXT_BYTES]


# ── download registry (extend here for future data sources) ───────────────
_DOWNLOAD_REGISTRY: dict[str, callable] = {
    "hk_data_gov": _hk_download_file,
}


def _tool_err(e: Exception) -> str:
    return f"[tool_error] {type(e).__name__}: {e}"


# ── tool factory ───────────────────────────────────────────────────────────
def dataset_tools(ctx: RunContext) -> list:  # noqa: ARG001
    @tool
    def search_datasets(query: str, top_k: int = 5) -> list[dict]:
        """Semantic search over the HK open-data catalog in Qdrant.

        Returns up to `top_k` results ranked by relevance to natural-language queries.
        Each result includes dataset_id, dataset_name, category, data_provider,
        data_format, resource_name, source, score, and page_url.
        Follow up with get_dataset_details(dataset_id) to list downloadable files.
        """
        try:
            resp = _openai().embeddings.create(input=[query], model=OPENAI_EMBED_MODEL)
            vec = resp.data[0].embedding
            response = _qdrant().query_points(
                collection_name=COLLECTION,
                query=vec,
                limit=top_k,
                with_payload=True,
            )
            return [
                {
                    **(h.payload or {}),
                    "score": round(h.score, 4),
                    "page_url": f"{_HK_PAGE_BASE}/{(h.payload or {}).get('dataset_id', '')}",
                }
                for h in response.points
            ]
        except Exception as e:
            return _tool_err(e)

    @tool
    def browse_datasets(query: str, limit: int = 10) -> dict:
        """Keyword search over the HK open-data catalog via the CKAN API.

        Complements search_datasets: use this when you want exact term matching
        or to browse by category/provider names.
        Returns count, has_more, and a list of matching datasets with their metadata.
        """
        try:
            result = _ckan_get("package_search", {"q": query, "rows": min(limit, 1000), "start": 0})
            return {
                "count": result.get("count", 0),
                "results": result.get("results", []),
                "has_more": result.get("count", 0) > limit,
            }
        except Exception as e:
            return _tool_err(e)

    @tool
    def get_dataset_details(dataset_id: str) -> dict:
        """Fetch full details and resource URLs for a dataset from data.gov.hk.

        Returns the dataset title, description, update frequency, and a list of
        resources (each with url, name, format, description).
        Pass a resource url to download_dataset_file to retrieve its data.
        """
        try:
            return _ckan_get("package_show", {"id": dataset_id})
        except Exception as e:
            return _tool_err(e)

    @tool
    def download_dataset_file(
        resource_url: str,
        source: str = "hk_data_gov",
        date: str = "",
    ) -> str:
        """Fetch a dataset resource file and return its content (≤200 rows / 8 KB).

        `resource_url`: direct file URL from get_dataset_details resources list.
        `date`: optional snapshot timestamp (YYYYMMDD or YYYYMMDD-HHMM from the
                historical archive); omit to get the most recent available version.
        `source`: data portal (default: hk_data_gov).
        JSON and CSV are returned as JSON arrays; other formats as plain text.
        """
        try:
            fn = _DOWNLOAD_REGISTRY.get(source)
            if fn is None:
                return f"Unknown source '{source}'. Available: {list(_DOWNLOAD_REGISTRY)}"
            return fn(resource_url, date)
        except Exception as e:
            return _tool_err(e)

    return [search_datasets, browse_datasets, get_dataset_details, download_dataset_file]
