# -*- coding: utf-8 -*-
"""Build a read-only SQL Server + warehouse.db catalog snapshot.

Usage from repository root:
    python scripts/build_sql_catalog.py
    python scripts/build_sql_catalog.py --policy config/sql_catalog_policy.local.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_project_env():
    # Backend-specific values win; root .env is the fallback used by the existing ETL scripts.
    for env_path in (BACKEND_DIR / ".env", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read SQL Server metadata and compare authorized objects with warehouse.db."
    )
    parser.add_argument(
        "--policy",
        default=(
            os.getenv("SQL_CATALOG_POLICY_PATH")
            or str(PROJECT_ROOT / "config" / "sql_catalog_policy.json")
        ),
        help="Local JSON allowlist/classification policy. If omitted, metadata visible in dbo is cataloged.",
    )
    parser.add_argument(
        "--mappings",
        default=str(PROJECT_ROOT / "config" / "warehouse_source_mappings.json"),
        help="JSON mapping from SQL Server sources to warehouse.db targets.",
    )
    parser.add_argument(
        "--warehouse",
        default=str(BACKEND_DIR / "warehouse.db"),
        help="Path to warehouse.db (opened read-only).",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "data" / "sql_catalog"),
        help="Generated output directory (data/ is gitignored).",
    )
    parser.add_argument(
        "--no-definitions",
        action="store_true",
        help="Do not read view/function/stored-procedure definitions for this run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_project_env()

    from local_warehouse import DB_PATH
    from query_engine import _get_engine
    from sql_catalog import (
        CatalogPolicy,
        build_catalog,
        load_mappings,
        load_policy,
        write_catalog_snapshot,
    )

    policy = load_policy(args.policy)
    if args.no_definitions:
        policy = CatalogPolicy(
            allowed_schemas=policy.allowed_schemas,
            allowed_objects=policy.allowed_objects,
            denied_objects=policy.denied_objects,
            sensitive_columns=policy.sensitive_columns,
            include_definitions=False,
            source_path=policy.source_path,
        )

    mappings = load_mappings(args.mappings)
    catalog = build_catalog(
        _get_engine("bravo"),
        args.warehouse or DB_PATH,
        policy=policy,
        mappings=mappings,
    )
    result = write_catalog_snapshot(catalog, args.output)

    summary = catalog["summary"]
    print(json.dumps({
        "ok": True,
        "database": catalog["source"].get("database"),
        "objects": summary["object_count"],
        "columns": summary["column_count"],
        "metadata_gaps": summary.get("metadata_gaps", []),
        "objects_without_read_permission": summary["objects_without_read_permission"],
        "warehouse_mapping_statuses": summary.get("warehouse_mapping_statuses", {}),
        "changed": result["changed"],
        "structural_hash": result["structural_hash"],
        "latest_path": result["latest_path"],
        "diff_path": result["diff_path"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
