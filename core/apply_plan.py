"""Pure Stage 14 planning and last-moment revalidation for layer updates."""

import math
from typing import Any, Dict, Mapping, Sequence

from .units import convert


FIELD_KEYS = (
    "material_field",
    "nominal_field",
    "internal_field",
    "hydraulic_field",
    "pressure_class_field",
)


def build_apply_plan(
    preview: Mapping[str, Any],
    current_records: Sequence[Mapping[str, Any]],
    field_mapping: Mapping[str, str],
    hydraulic_method: str,
) -> Dict[str, Any]:
    """Build a deterministic before/after plan without mutating a layer."""
    included = [row for row in preview.get("rows", []) if row.get("included")]
    if not included:
        raise ValueError("preview contains no included rows")
    selected_fields = {
        key: str(field_mapping.get(key) or "").strip() for key in FIELD_KEYS
    }
    mapped_names = [name for name in selected_fields.values() if name]
    if not mapped_names:
        raise ValueError("map at least one destination field")
    if len(mapped_names) != len(set(mapped_names)):
        raise ValueError("each destination field may be mapped only once")
    method = str(hydraulic_method).strip().upper()
    if method not in {"H-W", "D-W"}:
        raise ValueError("hydraulic method must be H-W or D-W")

    current_by_fid = _index_current_records(current_records)
    rows = []
    for preview_row in included:
        fid = int(preview_row["pipe_fid"])
        current = current_by_fid.get(fid)
        if current is None:
            raise ValueError(f"included pipe FID {fid} no longer exists")
        pipe_id = str(preview_row["pipe_id"]).strip()
        if str(current.get("id", "")).strip() != pipe_id:
            raise ValueError(
                f"pipe FID {fid} ID changed from {pipe_id!r} "
                f"to {current.get('id')!r}"
            )
        changes = {}
        for semantic, field_name in selected_fields.items():
            if not field_name:
                continue
            new_value = _proposed_value(
                semantic,
                preview_row,
                field_mapping,
                method,
            )
            old_value = current["values"].get(field_name)
            changes[field_name] = {
                "semantic": semantic,
                "old": old_value,
                "new": new_value,
                "changed": not values_equal(old_value, new_value),
            }
        changed = any(item["changed"] for item in changes.values())
        rows.append(
            {
                "pipe_fid": fid,
                "pipe_id": pipe_id,
                "catalog_id": preview_row["selected_catalog_id"],
                "material_code": preview_row["material_code"],
                "product_code": preview_row["product_code"],
                "status": "change" if changed else "maintained",
                "changes": changes,
            }
        )
    return {
        "rows": rows,
        "field_mapping": dict(field_mapping),
        "hydraulic_method": method,
        "included_count": len(rows),
        "change_count": sum(row["status"] == "change" for row in rows),
        "maintained_count": sum(row["status"] == "maintained" for row in rows),
        "memory_only": True,
    }


def revalidate_apply_plan(
    plan: Mapping[str, Any],
    current_records: Sequence[Mapping[str, Any]],
) -> None:
    """Reject a plan when any included ID or old target value changed."""
    current_by_fid = _index_current_records(current_records)
    for row in plan["rows"]:
        fid = int(row["pipe_fid"])
        current = current_by_fid.get(fid)
        if current is None:
            raise ValueError(f"pipe FID {fid} disappeared after preview")
        if str(current.get("id", "")).strip() != row["pipe_id"]:
            raise ValueError(f"pipe FID {fid} ID changed after preview")
        for field_name, change in row["changes"].items():
            if not values_equal(current["values"].get(field_name), change["old"]):
                raise ValueError(
                    f"pipe {row['pipe_id']} field {field_name} changed "
                    "after the apply plan was prepared"
                )


def revalidate_input_snapshot(
    original: Mapping[str, Any],
    current: Mapping[str, Any],
) -> None:
    """Reject apply when mapped pipe lengths, IDs, or result flows changed."""
    for category_key in ("pipe_id_category", "result_id_category"):
        if original.get(category_key) != current.get(category_key):
            raise ValueError(f"{category_key} changed after batch sizing")
    _compare_snapshot_records(
        "pipe",
        original.get("pipe_records", []),
        current.get("pipe_records", []),
        ("id", "length"),
    )
    _compare_snapshot_records(
        "result",
        original.get("result_records", []),
        current.get("result_records", []),
        ("id", "flow"),
    )


def format_apply_plan(plan: Mapping[str, Any], row_limit: int = 500) -> str:
    lines = [
        "HydroSizer Safe Apply Plan — Stage 14",
        "Mode: review only; no layer changes have been made",
        "",
        "Summary",
        f"  Included pipes: {plan['included_count']}",
        f"  Pipes with changes: {plan['change_count']}",
        f"  Maintained pipes: {plan['maintained_count']}",
        f"  Hydraulic method: {plan['hydraulic_method']}",
        "",
        "Mapped destination fields",
    ]
    for key in FIELD_KEYS:
        lines.append(f"  {key}: {plan['field_mapping'].get(key) or '<not mapped>'}")
    lines.extend(["", f"Rows ({len(plan['rows'])})"])
    for row in plan["rows"][:row_limit]:
        lines.append(
            f"  [{row['status'].upper()}] ID {row['pipe_id']} "
            f"fid={row['pipe_fid']} product="
            f"{row['material_code']}/{row['product_code']}"
        )
        for field_name, change in row["changes"].items():
            marker = "CHANGE" if change["changed"] else "KEEP"
            lines.append(
                f"      [{marker}] {field_name}: "
                f"{_display(change['old'])} -> {_display(change['new'])}"
            )
    if len(plan["rows"]) > row_limit:
        lines.append(f"  <limited to {row_limit} rows>")
    lines.extend(
        [
            "",
            "Safety boundary",
            "  Apply requires a separate confirmation dialog.",
            "  IDs and old values will be revalidated immediately before edits.",
            "  Critical failure destroys the edit command and prevents partial apply.",
            "  Successful edits remain pending in the QGIS edit buffer for undo/save.",
        ]
    )
    return "\n".join(lines)


def values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    try:
        left_number = float(left)
        right_number = float(right)
    except (TypeError, ValueError):
        return str(left) == str(right)
    if not math.isfinite(left_number) or not math.isfinite(right_number):
        return left_number == right_number
    return math.isclose(left_number, right_number, rel_tol=1e-12, abs_tol=1e-12)


def _index_current_records(records):
    indexed = {}
    for record in records:
        fid = int(record["fid"])
        if fid in indexed:
            raise ValueError(f"duplicate current pipe FID {fid}")
        indexed[fid] = record
    return indexed


def _compare_snapshot_records(label, original_records, current_records, keys):
    original = {int(record["fid"]): record for record in original_records}
    current = {int(record["fid"]): record for record in current_records}
    if len(original) != len(original_records) or len(current) != len(current_records):
        raise ValueError(f"duplicate {label} FID detected during revalidation")
    if set(original) != set(current):
        raise ValueError(f"{label} feature set changed after batch sizing")
    for fid, before in original.items():
        after = current[fid]
        for key in keys:
            if not values_equal(before.get(key), after.get(key)):
                raise ValueError(
                    f"{label} FID {fid} {key} changed after batch sizing"
                )


def _proposed_value(semantic, row, mapping, method):
    if semantic == "material_field":
        value = str(row.get("qgisred_material_value") or "").strip()
        if not value:
            raise ValueError(
                f"product {row['material_code']}/{row['product_code']} has no "
                "qgisred_material_value; unmap the material field or update the catalog"
            )
        return value
    if semantic == "nominal_field":
        return _diameter_value(
            row,
            "nominal_diameter",
            "nominal_diameter_unit",
            mapping.get("nominal_unit", "mm"),
        )
    if semantic == "internal_field":
        return _diameter_value(
            row,
            "internal_diameter",
            "internal_diameter_unit",
            mapping.get("internal_unit", "mm"),
        )
    if semantic == "pressure_class_field":
        value = str(row.get("pressure_class") or "").strip()
        if not value:
            raise ValueError(f"product {row['product_code']} has no pressure class")
        return value
    if semantic == "hydraulic_field":
        if method == "H-W":
            value = row.get("hazen_williams_c")
            if value is None:
                raise ValueError(f"product {row['product_code']} has no H-W C")
            return float(value)
        value = row.get("absolute_roughness")
        source_unit = row.get("roughness_unit")
        if value is None or not source_unit:
            raise ValueError(
                f"product {row['product_code']} has no absolute roughness"
            )
        return convert(
            value,
            "diameter",
            source_unit,
            mapping.get("roughness_unit", "mm"),
        )
    raise ValueError(f"unknown apply semantic: {semantic}")


def _diameter_value(row, value_key, unit_key, target_unit):
    value = row.get(value_key)
    source_unit = row.get(unit_key)
    if value is None or not source_unit:
        raise ValueError(f"product {row['product_code']} has no {value_key}")
    return convert(value, "diameter", source_unit, target_unit)


def _display(value):
    if value is None:
        return "<null>"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)
