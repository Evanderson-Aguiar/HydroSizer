"""Memory-only batch sizing orchestration for Stage 12."""

import math
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .combined_sizing import size_single_segment_combined
from .pressure import resolve_endpoint_pressure


ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]
PRODUCT_SNAPSHOT_FIELDS = (
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
    "qgisred_material_value",
)
CALCULATION_SNAPSHOT_FIELDS = (
    "reynolds",
    "regime",
    "friction_factor",
    "relative_roughness",
)
ENDPOINT_SNAPSHOT_FIELDS = (
    "initial_node_id",
    "final_node_id",
    "endpoint_pressure_unit",
    "initial_pressure_original",
    "final_pressure_original",
    "initial_pressure_pa",
    "final_pressure_pa",
    "base_verification_pressure_pa",
    "margin_mode",
    "safety_factor",
    "additive_margin_pa",
    "additive_margin_original",
    "additive_margin_unit",
)


def run_batch_sizing(
    validation_dataset: Mapping[str, Any],
    products: Sequence[Mapping[str, Any]],
    criteria: Mapping[str, Any],
    flow_unit: str,
    length_unit: str,
    selection_mode: str,
    selected_pipe_fids: Sequence[int],
    endpoint_dataset: Optional[Mapping[str, Any]] = None,
    endpoint_settings: Optional[Mapping[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_callback: Optional[CancelCallback] = None,
) -> Dict[str, Any]:
    """Size valid mapped pipes without mutating layers or catalog records."""
    mode = str(selection_mode).strip().casefold()
    if mode not in {"all", "selected"}:
        raise ValueError("selection mode must be all or selected")
    if not flow_unit:
        raise ValueError("flow unit is required")
    if not length_unit:
        raise ValueError("length unit is required")
    if not products:
        raise ValueError("active catalog contains no products")
    pressure_enabled = bool(criteria.get("pressure_enabled"))
    if pressure_enabled and (endpoint_dataset is None or endpoint_settings is None):
        raise ValueError(
            "endpoint pressure mapping is required when pressure is enabled"
        )

    selected_set = {int(fid) for fid in selected_pipe_fids}
    pipe_records = list(validation_dataset["pipe_records"])
    if mode == "selected":
        pipe_records = [
            record for record in pipe_records if int(record["fid"]) in selected_set
        ]
        if not pipe_records:
            raise ValueError("no mapped pipe feature is selected")
    pipe_records.sort(key=lambda record: int(record["fid"]))
    result_index = _result_index(validation_dataset)
    products_by_id = {
        int(product.get("catalog_id") or 0): product for product in products
    }
    total = len(pipe_records)
    rows = []
    cancelled = False
    for record in pipe_records:
        if cancel_callback is not None and cancel_callback():
            cancelled = True
            break
        pipe_id = _normalize_id(
            record["id"],
            validation_dataset["pipe_id_category"],
        )
        try:
            result_record = result_index[pipe_id]
            endpoint = None
            pipe_criteria = dict(criteria)
            pipe_criteria.update(
                {
                    "flow_value": result_record["flow"],
                    "flow_unit": flow_unit,
                    "length_value": record["length"],
                    "length_unit": length_unit,
                }
            )
            if pressure_enabled:
                endpoint = resolve_endpoint_pressure(
                    endpoint_dataset,
                    pipe_id,
                    endpoint_settings["pressure_unit"],
                    endpoint_settings["margin_mode"],
                    endpoint_settings["safety_factor"],
                    endpoint_settings["additive_margin_value"],
                    endpoint_settings["additive_margin_unit"],
                )
                pipe_criteria["verification_pressure_value"] = endpoint[
                    "verification_pressure_pa"
                ]
                pipe_criteria["verification_pressure_unit"] = "Pa"
            sizing = size_single_segment_combined(
                products=products,
                **pipe_criteria,
            )
            row = _successful_row(
                record,
                result_record,
                sizing,
                endpoint,
                products_by_id,
            )
        except (KeyError, ValueError) as error:
            row = _error_row(
                record,
                pipe_id,
                str(error),
                flow_unit,
                length_unit,
            )
        rows.append(row)
        if progress_callback is not None:
            progress_callback(len(rows), total, pipe_id)

    return {
        "selection_mode": mode,
        "total_requested": total,
        "processed_count": len(rows),
        "cancelled": cancelled,
        "rows": rows,
        "summary": _summary(rows),
        "criteria": dict(criteria),
        "flow_unit": flow_unit,
        "length_unit": length_unit,
        "memory_only": True,
    }


def format_batch_sizing_report(
    result: Mapping[str, Any],
    row_limit: int = 500,
) -> str:
    """Format Stage 12 status counts and per-pipe memory-only results."""
    summary = result["summary"]
    lines = [
        "HydroSizer Batch Sizing — Stage 12",
        "Mode: preview in memory only; no layer or catalog changes",
        "",
        "Run",
        f"  Selection mode: {result['selection_mode']}",
        f"  Requested pipes: {result['total_requested']}",
        f"  Processed pipes: {result['processed_count']}",
        f"  Cancelled: {'yes' if result['cancelled'] else 'no'}",
        "",
        "Summary",
        f"  Sized: {summary['sized']}",
        f"  Sized with warning: {summary['sized_with_warning']}",
        f"  No catalog solution: {summary['no_solution']}",
        f"  Insufficient data: {summary['insufficient_data']}",
        "",
        f"Results ({len(result['rows'])})",
    ]
    if not result["rows"]:
        lines.append("  <none>")
    for row in result["rows"][:row_limit]:
        lines.append(
            f"  [{row['status'].upper()}] ID {row['pipe_id']} "
            f"fid={row['pipe_fid']}"
        )
        if row["selected_catalog_id"] is not None:
            lines.append(
                f"      Product: {row['material_code']}/{row['product_code']} "
                f"(catalog ID {row['selected_catalog_id']})"
            )
            lines.append(
                f"      Q={_number(row['flow_original'])} {row['flow_unit']}; "
                f"L={_number(row['length_original'])} {row['length_unit']}; "
                f"V={_number(row['velocity_m_s'])} m/s"
            )
            lines.append(
                f"      J={_number(row['unit_headloss_m_km'])} m/km; "
                f"hf={_number(row['total_headloss_m'])} m; "
                f"cost={_optional(row['segment_cost'])}"
            )
            if row["verification_pressure_pa"] is not None:
                lines.append(
                    "      Endpoint pressure check: "
                    f"{_number(row['verification_pressure_pa'])} Pa"
                )
            lines.append(
                f"      Controlling criterion: {row['controlling_criterion']}"
            )
        if row["messages"]:
            lines.append("      Messages: " + "; ".join(row["messages"]))
    if len(result["rows"]) > row_limit:
        lines.append(
            f"  <report limited to {row_limit} of {len(result['rows'])} rows>"
        )
    lines.extend(
        [
            "",
            "Safety boundary",
            "  Results exist only in plugin memory and are cleared on reload.",
            "  Cancellation preserves no partial edits because no edits are started.",
            "  Filtering and inclusion are available in Sizing review.",
            "  There is no layer apply action in Stage 13.",
        ]
    )
    return "\n".join(lines)


def _result_index(dataset: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    index = {}
    for record in dataset["result_records"]:
        identifier = _normalize_id(record["id"], dataset["result_id_category"])
        if identifier in index:
            previous = float(index[identifier]["flow"])
            current = float(record["flow"])
            if previous != current:
                raise ValueError(
                    f"result ID {identifier!r} has conflicting flow values"
                )
            continue
        index[identifier] = record
    return index


def _successful_row(pipe, result_record, sizing, endpoint, products_by_id):
    selected = sizing["selected"]
    if selected is None:
        messages = []
        for candidate in sizing["evaluated"]:
            messages.extend(candidate.get("failures", []))
        row = {
            "pipe_fid": pipe["fid"],
            "pipe_id": str(pipe["id"]).strip(),
            "flow_original": result_record["flow"],
            "flow_unit": sizing["flow_unit"],
            "length_original": pipe["length"],
            "length_unit": sizing["length_unit"],
            "status": "no solution",
            "selected_catalog_id": None,
            "material_code": "",
            "product_code": "",
            "velocity_m_s": None,
            "unit_headloss_m_km": None,
            "total_headloss_m": None,
            "segment_cost": None,
            "verification_pressure_pa": (
                endpoint["verification_pressure_pa"] if endpoint else None
            ),
            "controlling_criterion": "",
            "messages": _unique(messages) or [
                "no active catalog product satisfies every required criterion"
            ],
        }
        row.update({field: None for field in PRODUCT_SNAPSHOT_FIELDS})
        row.update({field: None for field in CALCULATION_SNAPSHOT_FIELDS})
        row.update(_endpoint_snapshot(endpoint))
        return row
    messages = list(selected.get("warnings", []))
    messages.extend(sizing.get("warnings", []))
    if endpoint:
        messages.extend(endpoint.get("warnings", []))
    row = {
        "pipe_fid": pipe["fid"],
        "pipe_id": str(pipe["id"]).strip(),
        "flow_original": result_record["flow"],
        "flow_unit": sizing["flow_unit"],
        "length_original": pipe["length"],
        "length_unit": sizing["length_unit"],
        "status": selected["status"],
        "selected_catalog_id": selected["catalog_id"],
        "material_code": selected["material_code"],
        "product_code": selected["product_code"],
        "velocity_m_s": selected["velocity_m_s"],
        "unit_headloss_m_km": selected["unit_headloss_m_km"],
        "total_headloss_m": selected["total_headloss_m"],
        "segment_cost": selected["segment_cost"],
        "verification_pressure_pa": (
            endpoint["verification_pressure_pa"] if endpoint else None
        ),
        "controlling_criterion": selected["controlling_criterion"],
        "messages": _unique(messages),
    }
    product = products_by_id.get(int(selected["catalog_id"]), {})
    row.update({field: product.get(field) for field in PRODUCT_SNAPSHOT_FIELDS})
    row.update(
        {field: selected.get(field) for field in CALCULATION_SNAPSHOT_FIELDS}
    )
    row.update(_endpoint_snapshot(endpoint))
    return row


def _error_row(pipe, pipe_id, message, flow_unit, length_unit):
    row = {
        "pipe_fid": pipe["fid"],
        "pipe_id": pipe_id,
        "flow_original": None,
        "flow_unit": flow_unit,
        "length_original": pipe.get("length"),
        "length_unit": length_unit,
        "status": "insufficient data",
        "selected_catalog_id": None,
        "material_code": "",
        "product_code": "",
        "velocity_m_s": None,
        "unit_headloss_m_km": None,
        "total_headloss_m": None,
        "segment_cost": None,
        "verification_pressure_pa": None,
        "controlling_criterion": "",
        "messages": [message],
    }
    row.update({field: None for field in PRODUCT_SNAPSHOT_FIELDS})
    row.update({field: None for field in CALCULATION_SNAPSHOT_FIELDS})
    row.update(_endpoint_snapshot(None))
    return row


def _endpoint_snapshot(endpoint):
    snapshot = {
        field: endpoint.get(field) if endpoint else None
        for field in ENDPOINT_SNAPSHOT_FIELDS
        if field != "endpoint_pressure_unit"
    }
    snapshot["endpoint_pressure_unit"] = (
        endpoint.get("pressure_unit") if endpoint else None
    )
    return snapshot


def _summary(rows):
    return {
        "sized": sum(row["status"] == "sized" for row in rows),
        "sized_with_warning": sum(
            row["status"] == "sized with warning" for row in rows
        ),
        "no_solution": sum(row["status"] == "no solution" for row in rows),
        "insufficient_data": sum(
            row["status"] == "insufficient data" for row in rows
        ),
    }


def _normalize_id(value: Any, category: str) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError("ID is null or invalid")
    if category == "integer":
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError(f"ID {value!r} is not an integer")
        return str(int(number))
    text = str(value).strip()
    if not text:
        raise ValueError("ID is empty")
    return text


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def _number(value: float) -> str:
    return f"{value:.12g}"


def _optional(value: Any) -> str:
    return "<not available>" if value is None else _number(value)
