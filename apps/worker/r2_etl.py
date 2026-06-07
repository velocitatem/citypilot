"""ETL: Cloudflare R2 CSVs -> sandbox DuckDB.

Downloads every *.csv from the configured R2 bucket and loads each one as a
table (named after the file stem) into a DuckDB file that gets uploaded to the
sandbox at SANDBOX_DATA_DIR/agent.duckdb.
"""

import io
import logging
import os
import re
import tempfile
from pathlib import Path

import boto3
import duckdb
from botocore.config import Config

log = logging.getLogger("worker.r2_etl")


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _table_name(key: str) -> str:
    stem = Path(key).stem
    return re.sub(r"[^a-zA-Z0-9_]", "_", stem).strip("_").lower() or "data"


def build_duckdb_from_r2(dest_path: Path) -> dict[str, int]:
    """Download all CSVs from R2 and load into DuckDB at dest_path.

    Returns a dict of {table_name: row_count}.
    """
    bucket = os.environ["R2_BUCKET_NAME"]
    client = _r2_client()

    paginator = client.get_paginator("list_objects_v2")
    csv_keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(".csv"):
                csv_keys.append(obj["Key"])

    log.info("[r2_etl] found %d CSV(s) in bucket=%s", len(csv_keys), bucket)

    if dest_path.exists():
        dest_path.unlink()

    manifest: dict[str, int] = {}
    with duckdb.connect(str(dest_path)) as db:
        for key in csv_keys:
            tbl = _table_name(key)
            log.info("[r2_etl] loading key=%s -> table=%s", key, tbl)
            try:
                obj = client.get_object(Bucket=bucket, Key=key)
                data = obj["Body"].read()
                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name
                db.execute(
                    f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM read_csv_auto(?)",
                    [tmp_path],
                )
                Path(tmp_path).unlink(missing_ok=True)
                count = db.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                manifest[tbl] = count
                log.info("[r2_etl] loaded table=%s rows=%d", tbl, count)
            except Exception:
                log.exception("[r2_etl] failed to load key=%s", key)

    log.info("[r2_etl] duckdb written path=%s tables=%d", dest_path, len(manifest))
    return manifest
