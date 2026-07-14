"""Atomic CSV and JSON audit bundle writer for confirmed layer updates."""

import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Optional
from uuid import uuid4


CSV_FIELDS = (
    "timestamp",
    "run_id",
    "layer_name",
    "layer_source",
    "pipe_id",
    "old_material",
    "new_material",
    "old_nominal_diameter",
    "new_nominal_diameter",
    "old_internal_diameter",
    "new_internal_diameter",
    "old_pressure_class",
    "new_pressure_class",
    "old_roughness_or_c",
    "new_roughness_or_c",
    "status",
    "error_message",
)


def write_audit_bundle(
    directory: Path,
    plan: Mapping[str, Any],
    metadata: Mapping[str, Any],
    run_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Mapping[str, Any]:
    """Write one unique CSV/JSON pair, removing partial outputs on failure."""
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    if not target_directory.is_dir():
        raise NotADirectoryError(str(target_directory))
    moment = timestamp or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    identifier = run_id or str(uuid4())
    stamp = moment.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    csv_path = target_directory / f"hydrosizer_pipe_changes_{stamp}.csv"
    json_path = target_directory / f"hydrosizer_run_{stamp}.json"
    if csv_path.exists() or json_path.exists():
        raise FileExistsError("audit output name already exists")

    csv_temp = _temporary_path(target_directory, csv_path.name)
    json_temp = _temporary_path(target_directory, json_path.name)
    finalized = []
    try:
        _write_csv(csv_temp, plan, metadata, identifier, moment)
        json_data = dict(metadata)
        json_data.update(
            {
                "run_id": identifier,
                "timestamp_utc": moment.astimezone(timezone.utc).isoformat(),
                "processed_count": plan["included_count"],
                "changed_count": plan["change_count"],
                "maintained_count": plan["maintained_count"],
                "failure_count": 0,
                "changes_csv": str(csv_path),
                "metadata_json": str(json_path),
                "edit_state": "pending in QGIS edit buffer",
            }
        )
        _write_json(json_temp, json_data)
        os.replace(csv_temp, csv_path)
        finalized.append(csv_path)
        os.replace(json_temp, json_path)
        finalized.append(json_path)
    except Exception:
        for path in (csv_temp, json_temp):
            if path.exists():
                path.unlink()
        for path in finalized:
            if path.exists():
                path.unlink()
        raise
    return {
        "run_id": identifier,
        "timestamp_utc": moment.astimezone(timezone.utc).isoformat(),
        "csv_path": csv_path,
        "json_path": json_path,
    }


def _write_csv(path, plan, metadata, run_id, moment):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in plan["rows"]:
            material = _semantic_change(row, "material_field")
            nominal = _semantic_change(row, "nominal_field")
            internal = _semantic_change(row, "internal_field")
            pressure = _semantic_change(row, "pressure_class_field")
            hydraulic = _semantic_change(row, "hydraulic_field")
            writer.writerow(
                {
                    "timestamp": moment.astimezone(timezone.utc).isoformat(),
                    "run_id": run_id,
                    "layer_name": metadata.get("layer_name", ""),
                    "layer_source": metadata.get("layer_source", ""),
                    "pipe_id": row["pipe_id"],
                    "old_material": material.get("old", ""),
                    "new_material": material.get("new", ""),
                    "old_nominal_diameter": nominal.get("old", ""),
                    "new_nominal_diameter": nominal.get("new", ""),
                    "old_internal_diameter": internal.get("old", ""),
                    "new_internal_diameter": internal.get("new", ""),
                    "old_pressure_class": pressure.get("old", ""),
                    "new_pressure_class": pressure.get("new", ""),
                    "old_roughness_or_c": hydraulic.get("old", ""),
                    "new_roughness_or_c": hydraulic.get("new", ""),
                    "status": (
                        "applied" if row["status"] == "change" else "maintained"
                    ),
                    "error_message": "",
                }
            )


def _write_json(path, data):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _semantic_change(row, semantic):
    for change in row["changes"].values():
        if change["semantic"] == semantic:
            return change
    return {}


def _temporary_path(directory, name):
    descriptor, raw_path = tempfile.mkstemp(
        dir=directory,
        prefix=f".{name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return Path(raw_path)
