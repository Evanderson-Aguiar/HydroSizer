"""Memory-only result preview, filtering, inclusion, and CSV export."""

import csv
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Mapping, Sequence

from .units import convert


ELIGIBLE_STATUSES = {"sized", "sized with warning"}
STATUS_FILTERS = ELIGIBLE_STATUSES | {"no solution", "insufficient data"}
INCLUSION_FILTERS = {"all", "included", "excluded"}
CSV_FIELDS = (
    "included",
    "eligible",
    "pipe_fid",
    "pipe_id",
    "status",
    "selected_catalog_id",
    "material_code",
    "product_code",
    "qgisred_material_value",
    "nominal_diameter",
    "nominal_diameter_unit",
    "internal_diameter",
    "internal_diameter_unit",
    "pressure_class",
    "max_allowable_pressure",
    "pressure_unit",
    "hazen_williams_c",
    "absolute_roughness",
    "roughness_unit",
    "cost_per_length",
    "cost_length_unit",
    "reynolds",
    "regime",
    "friction_factor",
    "relative_roughness",
    "flow_original",
    "flow_unit",
    "length_original",
    "length_unit",
    "velocity_m_s",
    "unit_headloss_m_km",
    "total_headloss_m",
    "verification_pressure_pa",
    "verification_pressure_project",
    "verification_pressure_project_unit",
    "initial_node_id",
    "final_node_id",
    "endpoint_pressure_unit",
    "initial_pressure_original",
    "final_pressure_original",
    "initial_pressure_pa",
    "final_pressure_pa",
    "segment_cost",
    "controlling_criterion",
    "messages",
)


def create_preview(batch_result: Mapping[str, Any]) -> Dict[str, Any]:
    """Clone one batch result into an independently editable preview snapshot."""
    if not batch_result.get("memory_only"):
        raise ValueError("preview requires a memory-only batch result")
    rows = []
    seen_fids = set()
    for source in batch_result.get("rows", []):
        row = dict(source)
        fid = int(row["pipe_fid"])
        if fid in seen_fids:
            raise ValueError(f"preview contains duplicate pipe FID {fid}")
        seen_fids.add(fid)
        eligible = (
            row.get("status") in ELIGIBLE_STATUSES
            and row.get("selected_catalog_id") is not None
        )
        row["eligible"] = eligible
        row["included"] = eligible
        rows.append(row)
    preview = {
        "rows": rows,
        "source_cancelled": bool(batch_result.get("cancelled")),
        "memory_only": True,
    }
    preview["summary"] = preview_summary(preview)
    return preview


def filter_preview_rows(
    preview: Mapping[str, Any],
    search: str = "",
    status: str = "all",
    inclusion: str = "all",
) -> list:
    """Return stable preview rows matching text, status, and inclusion filters."""
    normalized_status = str(status).strip().casefold()
    normalized_inclusion = str(inclusion).strip().casefold()
    if normalized_status != "all" and normalized_status not in STATUS_FILTERS:
        raise ValueError("unknown preview status filter")
    if normalized_inclusion not in INCLUSION_FILTERS:
        raise ValueError("unknown preview inclusion filter")
    needle = str(search).strip().casefold()
    filtered = []
    for row in preview.get("rows", []):
        if normalized_status != "all" and row["status"] != normalized_status:
            continue
        if normalized_inclusion == "included" and not row["included"]:
            continue
        if normalized_inclusion == "excluded" and row["included"]:
            continue
        if needle and needle not in _searchable_text(row):
            continue
        filtered.append(row)
    return filtered


def set_preview_inclusion(
    preview: Dict[str, Any],
    pipe_fids: Sequence[int],
    included: bool,
) -> Dict[str, int]:
    """Change inclusion for eligible FIDs and return deterministic counts."""
    requested = {int(fid) for fid in pipe_fids}
    if not requested:
        raise ValueError("select at least one preview row")
    found = set()
    changed = 0
    ineligible = 0
    for row in preview.get("rows", []):
        fid = int(row["pipe_fid"])
        if fid not in requested:
            continue
        found.add(fid)
        if not row["eligible"]:
            ineligible += 1
            continue
        target = bool(included)
        if row["included"] != target:
            row["included"] = target
            changed += 1
    preview["summary"] = preview_summary(preview)
    return {
        "requested": len(requested),
        "found": len(found),
        "changed": changed,
        "ineligible": ineligible,
        "missing": len(requested - found),
    }


def preview_summary(preview: Mapping[str, Any]) -> Dict[str, int]:
    rows = list(preview.get("rows", []))
    return {
        "total": len(rows),
        "eligible": sum(bool(row.get("eligible")) for row in rows),
        "included": sum(bool(row.get("included")) for row in rows),
        "excluded": sum(not bool(row.get("included")) for row in rows),
    }


def preview_pressure_unit(
    rows: Sequence[Mapping[str, Any]],
    fallback: str = "Pa",
) -> str:
    """Return the pressure unit captured by the sizing snapshot."""
    for row in rows:
        unit = str(row.get("endpoint_pressure_unit") or "").strip()
        if unit:
            return unit
    return str(fallback or "Pa").strip() or "Pa"


def preview_pressure_value(
    row: Mapping[str, Any],
    pressure_unit: str,
):
    """Convert the internal verification pressure to a presentation unit."""
    value = row.get("verification_pressure_pa")
    if value is None:
        return None
    return convert(value, "pressure", "Pa", pressure_unit)


def export_preview_csv(
    target_path: Path,
    rows: Sequence[Mapping[str, Any]],
    pressure_unit: str = "Pa",
) -> int:
    """Atomically export the currently filtered preview rows as UTF-8 CSV."""
    if not rows:
        raise ValueError("the current preview filter contains no rows")
    target = Path(target_path)
    if not target.parent.is_dir():
        raise FileNotFoundError(f"Destination folder does not exist: {target.parent}")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            display_unit = preview_pressure_unit(rows, pressure_unit)
            for row in rows:
                record = {}
                for field in CSV_FIELDS:
                    value = row.get(field)
                    if field in {"included", "eligible"}:
                        value = "1" if value else "0"
                    elif field == "messages":
                        value = " | ".join(value or [])
                    elif field == "verification_pressure_project":
                        value = preview_pressure_value(row, display_unit)
                    elif field == "verification_pressure_project_unit":
                        value = display_unit
                    elif value is None:
                        value = ""
                    record[field] = value
                writer.writerow(record)
            temporary_path = Path(stream.name)
        os.replace(temporary_path, target)
    except Exception:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        raise
    return len(rows)


def _searchable_text(row: Mapping[str, Any]) -> str:
    values = (
        row.get("pipe_id"),
        row.get("pipe_fid"),
        row.get("status"),
        row.get("selected_catalog_id"),
        row.get("material_code"),
        row.get("product_code"),
        " ".join(row.get("messages") or []),
    )
    return " ".join("" if value is None else str(value) for value in values).casefold()
