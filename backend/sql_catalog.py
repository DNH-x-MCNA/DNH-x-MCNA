# -*- coding: utf-8 -*-
"""Read-only SQL Server/SQLite catalog used by the chatbot data-access roadmap.

This module deliberately reads metadata only. It never samples business rows and never executes
stored procedures. Full object definitions are included only when the applied policy allows them.
"""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text


CATALOG_VERSION = 1
SQL_OBJECT_TYPES = ("U", "V", "P", "FN", "IF", "TF")


SERVER_INFO_SQL = """
SELECT
    DB_NAME() AS database_name,
    CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version,
    CAST(SERVERPROPERTY('Edition') AS nvarchar(128)) AS edition
"""

OBJECTS_SQL = """
SELECT
    o.object_id,
    s.name AS schema_name,
    o.name AS object_name,
    o.type AS object_type,
    o.type_desc,
    CONVERT(varchar(33), o.create_date, 126) AS create_date,
    CONVERT(varchar(33), o.modify_date, 126) AS modify_date,
    COALESCE(SUM(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END), 0) AS row_count_estimate,
    CAST(ep.value AS nvarchar(4000)) AS description,
    CASE
        WHEN o.type = 'P' THEN HAS_PERMS_BY_NAME(QUOTENAME(s.name) + '.' + QUOTENAME(o.name), 'OBJECT', 'EXECUTE')
        ELSE HAS_PERMS_BY_NAME(QUOTENAME(s.name) + '.' + QUOTENAME(o.name), 'OBJECT', 'SELECT')
    END AS has_read_permission
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id = o.schema_id
LEFT JOIN sys.partitions p ON p.object_id = o.object_id
LEFT JOIN sys.extended_properties ep
    ON ep.major_id = o.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
WHERE o.is_ms_shipped = 0 AND o.type IN ('U', 'V', 'P', 'FN', 'IF', 'TF')
GROUP BY o.object_id, s.name, o.name, o.type, o.type_desc, o.create_date, o.modify_date, ep.value
"""

COLUMNS_SQL = """
SELECT
    c.object_id,
    c.column_id,
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    c.is_identity,
    c.is_computed,
    c.collation_name,
    dc.definition AS default_definition,
    cc.definition AS computed_definition,
    CAST(ep.value AS nvarchar(4000)) AS description
FROM sys.columns c
JOIN sys.types t ON t.user_type_id = c.user_type_id
JOIN sys.objects o ON o.object_id = c.object_id AND o.is_ms_shipped = 0
LEFT JOIN sys.default_constraints dc
    ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
LEFT JOIN sys.computed_columns cc
    ON cc.object_id = c.object_id AND cc.column_id = c.column_id
LEFT JOIN sys.extended_properties ep
    ON ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
WHERE o.type IN ('U', 'V', 'FN', 'IF', 'TF')
ORDER BY c.object_id, c.column_id
"""

INDEXES_SQL = """
SELECT
    i.object_id,
    i.index_id,
    i.name AS index_name,
    i.type_desc,
    i.is_unique,
    i.is_primary_key,
    i.has_filter,
    i.filter_definition,
    ic.key_ordinal,
    ic.index_column_id,
    ic.is_included_column,
    ic.is_descending_key,
    c.name AS column_name
FROM sys.indexes i
JOIN sys.objects o ON o.object_id = i.object_id AND o.is_ms_shipped = 0
LEFT JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
LEFT JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE o.type IN ('U', 'V') AND i.index_id > 0 AND i.is_hypothetical = 0
ORDER BY i.object_id, i.index_id, ic.is_included_column, ic.key_ordinal, ic.index_column_id
"""

FOREIGN_KEYS_SQL = """
SELECT
    fk.object_id AS foreign_key_id,
    fk.name AS foreign_key_name,
    fk.parent_object_id,
    ps.name AS parent_schema,
    po.name AS parent_object,
    pc.name AS parent_column,
    rs.name AS referenced_schema,
    ro.name AS referenced_object,
    rc.name AS referenced_column,
    fkc.constraint_column_id,
    fk.delete_referential_action_desc,
    fk.update_referential_action_desc,
    fk.is_disabled,
    fk.is_not_trusted
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.objects po ON po.object_id = fk.parent_object_id
JOIN sys.schemas ps ON ps.schema_id = po.schema_id
JOIN sys.columns pc ON pc.object_id = po.object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.objects ro ON ro.object_id = fk.referenced_object_id
JOIN sys.schemas rs ON rs.schema_id = ro.schema_id
JOIN sys.columns rc ON rc.object_id = ro.object_id AND rc.column_id = fkc.referenced_column_id
ORDER BY fk.parent_object_id, fk.object_id, fkc.constraint_column_id
"""

DEPENDENCIES_SQL = """
SELECT
    d.referencing_id,
    d.referenced_id,
    d.referenced_server_name,
    d.referenced_database_name,
    d.referenced_schema_name,
    d.referenced_entity_name,
    rc.name AS referenced_minor_name,
    d.is_schema_bound_reference,
    d.is_ambiguous
FROM sys.sql_expression_dependencies d
JOIN sys.objects o ON o.object_id = d.referencing_id AND o.is_ms_shipped = 0
LEFT JOIN sys.columns rc
    ON rc.object_id = d.referenced_id AND rc.column_id = d.referenced_minor_id
WHERE o.type IN ('V', 'P', 'FN', 'IF', 'TF')
ORDER BY d.referencing_id, d.referenced_schema_name, d.referenced_entity_name, rc.name
"""

DEFINITIONS_SQL = """
SELECT m.object_id, m.definition
FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id
WHERE o.is_ms_shipped = 0 AND o.type IN ('V', 'P', 'FN', 'IF', 'TF')
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rows(connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(text(sql)).mappings().all()]


def _optional_rows(connection, section: str, sql: str, metadata_gaps: list[dict[str, str]]):
    try:
        return _rows(connection, sql)
    except Exception as exc:
        message = str(getattr(exc, "orig", exc)).replace("\n", " ")[:500]
        reason = "permission_denied" if "permission was denied" in message.lower() else "query_failed"
        metadata_gaps.append({"section": section, "reason": reason, "detail": message})
        return []


def _matches(value: str, patterns: Iterable[str]) -> bool:
    lowered = value.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in patterns)


@dataclass(frozen=True)
class CatalogPolicy:
    allowed_schemas: tuple[str, ...] = ("dbo",)
    allowed_objects: tuple[str, ...] = ()
    denied_objects: tuple[str, ...] = ()
    sensitive_columns: dict[str, str] = field(default_factory=dict)
    include_definitions: bool = True
    source_path: str | None = None

    def allows_object(self, schema_name: str, object_name: str) -> bool:
        full_name = f"{schema_name}.{object_name}"
        if self.allowed_schemas and schema_name.lower() not in {s.lower() for s in self.allowed_schemas}:
            return False
        if self.allowed_objects and not _matches(full_name, self.allowed_objects):
            return False
        return not _matches(full_name, self.denied_objects)

    def classification_for(self, schema_name: str, object_name: str, column_name: str) -> str | None:
        full_name = f"{schema_name}.{object_name}.{column_name}"
        for pattern, classification in self.sensitive_columns.items():
            if _matches(full_name, (pattern,)):
                return classification
        return None

    def public_summary(self) -> dict[str, Any]:
        return {
            "allowed_schemas": list(self.allowed_schemas),
            "allowed_objects": list(self.allowed_objects),
            "denied_objects": list(self.denied_objects),
            "include_definitions": self.include_definitions,
            "classified_column_patterns": len(self.sensitive_columns),
            "source_path": self.source_path,
        }


def load_policy(path: str | os.PathLike[str] | None = None) -> CatalogPolicy:
    if not path:
        return CatalogPolicy(source_path=None)
    policy_path = Path(path).resolve()
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    return CatalogPolicy(
        allowed_schemas=tuple(raw.get("allowed_schemas") or ("dbo",)),
        allowed_objects=tuple(raw.get("allowed_objects") or ()),
        denied_objects=tuple(raw.get("denied_objects") or ()),
        sensitive_columns=dict(raw.get("sensitive_columns") or {}),
        include_definitions=bool(raw.get("include_definitions", True)),
        source_path=str(policy_path),
    )


def _sql_type(column: dict[str, Any]) -> str:
    data_type = str(column.get("data_type") or "")
    data_type_lower = data_type.lower()
    max_length = int(column.get("max_length") or 0)
    if data_type_lower in ("varchar", "char", "varbinary", "binary"):
        length = "max" if max_length == -1 else str(max_length)
        return f"{data_type}({length})"
    if data_type_lower in ("nvarchar", "nchar"):
        length = "max" if max_length == -1 else str(max_length // 2)
        return f"{data_type}({length})"
    if data_type_lower in ("decimal", "numeric"):
        return f"{data_type}({column.get('precision')},{column.get('scale')})"
    if data_type_lower in ("datetime2", "datetimeoffset", "time"):
        return f"{data_type}({column.get('scale')})"
    return data_type


def extract_sql_server_catalog(engine, policy: CatalogPolicy | None = None) -> dict[str, Any]:
    """Read authorized SQL Server metadata. No business rows or procedure execution are performed."""
    policy = policy or CatalogPolicy()
    metadata_gaps: list[dict[str, str]] = []
    with engine.connect() as connection:
        server_info = _rows(connection, SERVER_INFO_SQL)[0]
        object_rows = _rows(connection, OBJECTS_SQL)
        column_rows = _rows(connection, COLUMNS_SQL)
        index_rows = _optional_rows(connection, "indexes", INDEXES_SQL, metadata_gaps)
        foreign_key_rows = _optional_rows(connection, "foreign_keys", FOREIGN_KEYS_SQL, metadata_gaps)
        dependency_rows = _optional_rows(connection, "dependencies", DEPENDENCIES_SQL, metadata_gaps)
        definition_rows = (
            _optional_rows(connection, "definitions", DEFINITIONS_SQL, metadata_gaps)
            if policy.include_definitions else []
        )

    objects: dict[int, dict[str, Any]] = {}
    for row in object_rows:
        if not policy.allows_object(row["schema_name"], row["object_name"]):
            continue
        object_id = int(row["object_id"])
        objects[object_id] = {
            "schema": row["schema_name"],
            "name": row["object_name"],
            "full_name": f"{row['schema_name']}.{row['object_name']}",
            "object_type": str(row["object_type"]).strip(),
            "type_desc": row["type_desc"],
            "description": row.get("description"),
            "create_date": row.get("create_date"),
            "modify_date": row.get("modify_date"),
            "row_count_estimate": int(row.get("row_count_estimate") or 0),
            "has_read_permission": bool(row.get("has_read_permission")),
            "columns": [],
            "indexes": [],
            "foreign_keys": [],
            "dependencies": [],
            "definition": None,
        }

    for row in column_rows:
        obj = objects.get(int(row["object_id"]))
        if not obj:
            continue
        obj["columns"].append({
            "ordinal": int(row["column_id"]),
            "name": row["column_name"],
            "data_type": _sql_type(row),
            "nullable": bool(row["is_nullable"]),
            "identity": bool(row["is_identity"]),
            "computed": bool(row["is_computed"]),
            "collation": row.get("collation_name"),
            "default_definition": row.get("default_definition"),
            "computed_definition": row.get("computed_definition"),
            "description": row.get("description"),
            "data_classification": policy.classification_for(
                obj["schema"], obj["name"], row["column_name"]
            ),
        })

    indexes_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for row in index_rows:
        object_id = int(row["object_id"])
        if object_id not in objects:
            continue
        key = (object_id, int(row["index_id"]))
        index = indexes_by_key.setdefault(key, {
            "name": row.get("index_name"),
            "type_desc": row.get("type_desc"),
            "unique": bool(row.get("is_unique")),
            "primary_key": bool(row.get("is_primary_key")),
            "filter_definition": row.get("filter_definition") if row.get("has_filter") else None,
            "key_columns": [],
            "included_columns": [],
        })
        if row.get("column_name"):
            if row.get("is_included_column"):
                index["included_columns"].append(row["column_name"])
            else:
                suffix = " DESC" if row.get("is_descending_key") else " ASC"
                index["key_columns"].append(f"{row['column_name']}{suffix}")
    for (object_id, _), index in indexes_by_key.items():
        objects[object_id]["indexes"].append(index)

    foreign_keys: dict[tuple[int, int], dict[str, Any]] = {}
    for row in foreign_key_rows:
        object_id = int(row["parent_object_id"])
        if object_id not in objects:
            continue
        key = (object_id, int(row["foreign_key_id"]))
        fk = foreign_keys.setdefault(key, {
            "name": row["foreign_key_name"],
            "referenced_object": f"{row['referenced_schema']}.{row['referenced_object']}",
            "columns": [],
            "delete_action": row["delete_referential_action_desc"],
            "update_action": row["update_referential_action_desc"],
            "disabled": bool(row["is_disabled"]),
            "not_trusted": bool(row["is_not_trusted"]),
        })
        fk["columns"].append({
            "column": row["parent_column"],
            "referenced_column": row["referenced_column"],
        })
    for (object_id, _), foreign_key in foreign_keys.items():
        objects[object_id]["foreign_keys"].append(foreign_key)

    allowed_full_names = {obj["full_name"].lower() for obj in objects.values()}
    for row in dependency_rows:
        obj = objects.get(int(row["referencing_id"]))
        if not obj:
            continue
        schema = row.get("referenced_schema_name") or "dbo"
        entity = row.get("referenced_entity_name")
        if not entity:
            continue
        local_referenced = f"{schema}.{entity}"
        parts = [row.get("referenced_server_name"), row.get("referenced_database_name"), schema, entity]
        referenced = ".".join(str(part) for part in parts if part)
        obj["dependencies"].append({
            "referenced_object": referenced,
            "referenced_column": row.get("referenced_minor_name"),
            "referenced_in_catalog": local_referenced.lower() in allowed_full_names,
            "schema_bound": bool(row.get("is_schema_bound_reference")),
            "ambiguous": bool(row.get("is_ambiguous")),
        })

    for row in definition_rows:
        obj = objects.get(int(row["object_id"]))
        if obj:
            obj["definition"] = row.get("definition")

    ordered_objects = sorted(objects.values(), key=lambda item: item["full_name"].lower())
    definition_objects = [
        obj for obj in ordered_objects if obj["object_type"] in ("V", "P", "FN", "IF", "TF")
    ]
    objects_without_definition = [
        obj["full_name"] for obj in definition_objects if not obj.get("definition")
    ]
    if policy.include_definitions and objects_without_definition:
        metadata_gaps.append({
            "section": "definitions",
            "reason": "partial_visibility_or_encrypted",
            "detail": f"{len(objects_without_definition)}/{len(definition_objects)} module definitions unavailable",
        })
    object_type_counts = Counter(obj["type_desc"] for obj in ordered_objects)
    all_columns = [column for obj in ordered_objects for column in obj["columns"]]
    catalog = {
        "catalog_version": CATALOG_VERSION,
        "generated_at": _utc_now(),
        "source": {
            "kind": "sql_server",
            "database": server_info.get("database_name"),
            "product_version": server_info.get("product_version"),
            "edition": server_info.get("edition"),
        },
        "policy": policy.public_summary(),
        "summary": {
            "object_count": len(ordered_objects),
            "object_types": dict(sorted(object_type_counts.items())),
            "column_count": len(all_columns),
            "columns_with_description": sum(bool(column.get("description")) for column in all_columns),
            "classified_column_count": sum(bool(column.get("data_classification")) for column in all_columns),
            "module_definition_count": sum(bool(obj.get("definition")) for obj in definition_objects),
            "objects_without_definition": objects_without_definition,
            "metadata_gaps": metadata_gaps,
            "objects_without_read_permission": [
                obj["full_name"] for obj in ordered_objects if not obj["has_read_permission"]
            ],
        },
        "objects": ordered_objects,
    }
    return catalog


def _sqlite_quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def extract_warehouse_catalog(db_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Inspect warehouse.db in SQLite read-only mode; no table data is sampled."""
    resolved = Path(db_path).resolve()
    if not resolved.exists():
        return {"kind": "sqlite", "path": str(resolved), "available": False, "objects": []}

    uri = f"file:{resolved.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        object_rows = connection.execute(
            "SELECT name, type, sql FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY lower(name)"
        ).fetchall()
        objects = []
        object_names = {row[0] for row in object_rows}
        sync_rows = {}
        if "sync_meta" in object_names:
            sync_rows = {
                row[0]: {
                    "last_synced_at": row[1],
                    "earliest_synced_date": row[2],
                    "latest_synced_date": row[3],
                }
                for row in connection.execute(
                    "SELECT table_name, last_synced_at, earliest_synced_date, latest_synced_date FROM sync_meta"
                ).fetchall()
            }

        for name, object_type, definition in object_rows:
            columns = []
            for row in connection.execute(f"PRAGMA table_xinfo({_sqlite_quote(name)})").fetchall():
                columns.append({
                    "ordinal": int(row[0]) + 1,
                    "name": row[1],
                    "data_type": row[2],
                    "nullable": not bool(row[3]),
                    "default_definition": row[4],
                    "primary_key_ordinal": int(row[5] or 0),
                    "hidden": bool(row[6]) if len(row) > 6 else False,
                })
            indexes = []
            for index_row in connection.execute(f"PRAGMA index_list({_sqlite_quote(name)})").fetchall():
                index_name = index_row[1]
                index_columns = [
                    col[2]
                    for col in connection.execute(
                        f"PRAGMA index_info({_sqlite_quote(index_name)})"
                    ).fetchall()
                ]
                indexes.append({
                    "name": index_name,
                    "unique": bool(index_row[2]),
                    "origin": index_row[3] if len(index_row) > 3 else None,
                    "partial": bool(index_row[4]) if len(index_row) > 4 else False,
                    "columns": index_columns,
                })
            foreign_keys = [
                {
                    "referenced_object": row[2],
                    "column": row[3],
                    "referenced_column": row[4],
                    "update_action": row[5],
                    "delete_action": row[6],
                }
                for row in connection.execute(f"PRAGMA foreign_key_list({_sqlite_quote(name)})").fetchall()
            ]
            objects.append({
                "name": name,
                "object_type": object_type,
                "definition": definition,
                "columns": columns,
                "indexes": indexes,
                "foreign_keys": foreign_keys,
                "sync_meta": sync_rows.get(name),
            })
    finally:
        connection.close()

    return {
        "kind": "sqlite",
        "path": str(resolved),
        "available": True,
        "object_count": len(objects),
        "objects": objects,
    }


def load_mappings(path: str | os.PathLike[str] | None) -> list[dict[str, Any]]:
    if not path:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    mappings = raw.get("mappings", raw) if isinstance(raw, dict) else raw
    if not isinstance(mappings, list):
        raise ValueError("warehouse mappings must be a list or an object containing 'mappings'")
    return [dict(mapping) for mapping in mappings]


def compare_source_to_warehouse(
    sql_catalog: dict[str, Any], warehouse_catalog: dict[str, Any], mappings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    source_names = {obj["full_name"].lower() for obj in sql_catalog.get("objects", [])}
    target_names = {obj["name"].lower() for obj in warehouse_catalog.get("objects", [])}
    output = []
    for mapping in mappings:
        source = str(mapping["source"])
        target = str(mapping["target"])
        has_source = source.lower() in source_names
        has_target = target.lower() in target_names
        if has_source and has_target:
            status = "ok"
        elif not has_source and not has_target:
            status = "missing_both"
        elif not has_source:
            status = "missing_source"
        else:
            status = "missing_target"
        output.append({**mapping, "source_present": has_source, "target_present": has_target, "status": status})
    return output


def build_catalog(
    engine,
    warehouse_db_path: str | os.PathLike[str],
    policy: CatalogPolicy | None = None,
    mappings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = extract_sql_server_catalog(engine, policy)
    catalog["warehouse"] = extract_warehouse_catalog(warehouse_db_path)
    catalog["warehouse_mappings"] = compare_source_to_warehouse(
        catalog, catalog["warehouse"], mappings or []
    )
    mapping_statuses = Counter(mapping["status"] for mapping in catalog["warehouse_mappings"])
    catalog["summary"]["warehouse_mapping_statuses"] = dict(sorted(mapping_statuses.items()))
    return catalog


def _remove_runtime_fields(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, child in value.items():
            if key in {
                "generated_at", "row_count_estimate", "last_synced_at", "path", "source_path",
                "structural_hash",
            }:
                continue
            cleaned[key] = _remove_runtime_fields(child)
        return cleaned
    if isinstance(value, list):
        return [_remove_runtime_fields(child) for child in value]
    return value


def structural_hash(catalog: dict[str, Any]) -> str:
    payload = json.dumps(
        _remove_runtime_fields(catalog), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _object_hash(obj: dict[str, Any]) -> str:
    payload = json.dumps(_remove_runtime_fields(obj), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def diff_catalogs(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {
            "from_hash": None,
            "to_hash": structural_hash(current),
            "sql_objects_added": [obj["full_name"] for obj in current.get("objects", [])],
            "sql_objects_removed": [],
            "sql_objects_changed": [],
            "warehouse_objects_added": [obj["name"] for obj in current.get("warehouse", {}).get("objects", [])],
            "warehouse_objects_removed": [],
            "warehouse_objects_changed": [],
        }

    def compare(previous_items, current_items, key_name):
        before = {item[key_name].lower(): item for item in previous_items}
        after = {item[key_name].lower(): item for item in current_items}
        added = sorted(after[key][key_name] for key in after.keys() - before.keys())
        removed = sorted(before[key][key_name] for key in before.keys() - after.keys())
        changed = sorted(
            after[key][key_name]
            for key in before.keys() & after.keys()
            if _object_hash(before[key]) != _object_hash(after[key])
        )
        return added, removed, changed

    sql_added, sql_removed, sql_changed = compare(
        previous.get("objects", []), current.get("objects", []), "full_name"
    )
    wh_added, wh_removed, wh_changed = compare(
        previous.get("warehouse", {}).get("objects", []),
        current.get("warehouse", {}).get("objects", []),
        "name",
    )
    return {
        "from_hash": structural_hash(previous),
        "to_hash": structural_hash(current),
        "sql_objects_added": sql_added,
        "sql_objects_removed": sql_removed,
        "sql_objects_changed": sql_changed,
        "warehouse_objects_added": wh_added,
        "warehouse_objects_removed": wh_removed,
        "warehouse_objects_changed": wh_changed,
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)
            stream.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def render_markdown(catalog: dict[str, Any]) -> str:
    summary = catalog["summary"]
    lines = [
        "# SQL Server catalog — Dược Nam Hà",
        "",
        f"Generated: `{catalog['generated_at']}`",
        f"Database: `{catalog['source'].get('database')}`",
        f"Structural hash: `{catalog.get('structural_hash', structural_hash(catalog))}`",
        "",
        "## Coverage",
        "",
        f"- Objects: **{summary['object_count']}**",
        f"- Columns: **{summary['column_count']}**",
        f"- Columns with MS_Description: **{summary['columns_with_description']}**",
        f"- Classified sensitive columns: **{summary['classified_column_count']}**",
        f"- SQL Server → warehouse mapping: `{summary.get('warehouse_mapping_statuses', {})}`",
        f"- Metadata gaps: `{summary.get('metadata_gaps', [])}`",
        "",
        "> This file contains metadata and definitions only; it contains no sampled business rows.",
        "",
    ]
    for obj in catalog.get("objects", []):
        lines.extend([
            f"## `{obj['full_name']}`",
            "",
            f"Type: `{obj['type_desc']}` · read permission: `{obj['has_read_permission']}` · "
            f"estimated rows: `{obj['row_count_estimate']}`",
            "",
            obj.get("description") or "_Business description not supplied in SQL Server metadata._",
            "",
        ])
        if obj["columns"]:
            lines.extend([
                "| # | Column | Type | Nullable | Classification | Description |",
                "|---:|---|---|:---:|---|---|",
            ])
            for column in obj["columns"]:
                description = str(column.get("description") or "").replace("|", "\\|").replace("\n", " ")
                lines.append(
                    f"| {column['ordinal']} | `{column['name']}` | `{column['data_type']}` | "
                    f"{'yes' if column['nullable'] else 'no'} | "
                    f"{column.get('data_classification') or ''} | {description} |"
                )
            lines.append("")
        if obj["dependencies"]:
            dependencies = sorted({dep["referenced_object"] for dep in obj["dependencies"]})
            lines.append("Dependencies: " + ", ".join(f"`{dependency}`" for dependency in dependencies))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_catalog_snapshot(catalog: dict[str, Any], output_dir: str | os.PathLike[str]) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    latest_path = output / "latest.json"
    previous = None
    if latest_path.exists():
        previous = json.loads(latest_path.read_text(encoding="utf-8"))

    current = copy.deepcopy(catalog)
    current_hash = structural_hash(current)
    current["structural_hash"] = current_hash
    changed = previous is None or structural_hash(previous) != current_hash
    diff = diff_catalogs(previous, current)

    _atomic_json_write(latest_path, current)
    markdown_path = output / "latest.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with markdown_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(render_markdown(current))

    snapshot_path = None
    diff_path = None
    if changed:
        stamp = current["generated_at"].replace(":", "").replace("-", "")
        snapshot_path = output / "snapshots" / f"{stamp}_{current_hash[:12]}.json"
        diff_path = output / "diffs" / f"{stamp}_{current_hash[:12]}.json"
        _atomic_json_write(snapshot_path, current)
        _atomic_json_write(diff_path, diff)

    return {
        "changed": changed,
        "structural_hash": current_hash,
        "latest_path": str(latest_path),
        "markdown_path": str(markdown_path),
        "snapshot_path": str(snapshot_path) if snapshot_path else None,
        "diff_path": str(diff_path) if diff_path else None,
        "diff": diff,
    }
