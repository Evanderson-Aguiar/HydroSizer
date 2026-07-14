"""Isolated, read-only adapter for QGISRed `*_Options.dbf` files."""

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


InspectionResult = Dict[str, Any]

FLOW_UNIT_MAP = {
    "LPS": ("L/s", "SI", True),
    "CMS": ("m³/s", "SI", True),
    "CMH": ("m³/h", "SI", True),
    "GPM": ("GPM", "US customary", True),
    "CFS": ("CFS", "US customary", True),
    "LPM": ("L/min", "SI", False),
    "MLD": ("ML/d", "SI", False),
    "CMD": ("m³/d", "SI", False),
    "MGD": ("MGD", "US customary", False),
    "IMGD": ("Imp MGD", "US customary", False),
    "AFD": ("acre-ft/day", "US customary", False),
}

HEADLOSS_METHOD_MAP = {
    "H-W": ("Hazen–Williams", True),
    "D-W": ("Darcy–Weisbach", True),
    "C-M": ("Chezy–Manning", False),
}


def inspect_options_dbf(
    options_path: Path, record_limit: int = 500
) -> InspectionResult:
    """Open a DBF through QGIS/OGR without adding it to the project.

    Records are read for inspection only. The adapter never starts editing,
    changes attributes, or writes sidecar files.
    """
    from qgis.core import NULL, QgsVectorLayer

    path = Path(options_path).resolve(strict=True)
    if path.suffix.casefold() != ".dbf":
        raise ValueError(f"Expected a DBF file: {path}")
    if record_limit < 1:
        raise ValueError("record_limit must be at least 1")

    before_stat = path.stat()
    layer = QgsVectorLayer(str(path), "HydroSizer options inspection", "ogr")
    if not layer.isValid():
        raise ValueError(f"QGIS/OGR could not open the DBF: {path}")

    fields = [
        {
            "name": field.name(),
            "type": field.typeName(),
            "length": field.length(),
            "precision": field.precision(),
        }
        for field in layer.fields()
    ]
    field_names = [field["name"] for field in fields]
    records = []
    for index, feature in enumerate(layer.getFeatures()):
        if index >= record_limit:
            break
        record = {}
        for field_name in field_names:
            value = feature[field_name]
            record[field_name] = None if value is None or value == NULL else _json_safe(value)
        records.append(record)

    provider = layer.dataProvider()
    encoding_method = getattr(provider, "encoding", None)
    encoding = encoding_method() if callable(encoding_method) else ""
    after_stat = path.stat()
    if (
        before_stat.st_size != after_stat.st_size
        or before_stat.st_mtime_ns != after_stat.st_mtime_ns
    ):
        raise RuntimeError("The DBF changed while it was being inspected.")

    feature_count = layer.featureCount()
    semantics = analyze_options_records(records)
    if not path.name.casefold().endswith("_options.dbf"):
        semantics["warnings"].append(
            "The selected filename does not match `*_Options.dbf`."
        )
    return {
        "path": str(path),
        "network_base": (
            path.name[: -len("_Options.dbf")]
            if path.name.casefold().endswith("_options.dbf")
            else ""
        ),
        "provider": layer.providerType(),
        "encoding": encoding,
        "file_size": before_stat.st_size,
        "last_modified_ns": before_stat.st_mtime_ns,
        "feature_count": feature_count,
        "record_limit": record_limit,
        "records_truncated": feature_count > len(records),
        "fields": fields,
        "records": records,
        "semantics": semantics,
        "read_only": True,
    }


def analyze_options_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Recognize the validated Group/Name/Value options schema."""
    warnings: List[str] = []
    if not records:
        return {
            "schema_recognized": False,
            "field_mapping": {},
            "flow_units_code": "",
            "flow_unit": "",
            "unit_system": "",
            "flow_unit_supported": False,
            "headloss_code": "",
            "hydraulic_method": "",
            "hydraulic_method_supported": False,
            "warnings": ["The options table contains no records."],
        }

    available_fields = {
        str(field).strip().casefold(): str(field) for field in records[0].keys()
    }
    required = ("group", "name", "value")
    if not all(field in available_fields for field in required):
        missing = [field for field in required if field not in available_fields]
        return {
            "schema_recognized": False,
            "field_mapping": {},
            "flow_units_code": "",
            "flow_unit": "",
            "unit_system": "",
            "flow_unit_supported": False,
            "headloss_code": "",
            "hydraulic_method": "",
            "hydraulic_method_supported": False,
            "warnings": [
                "Unrecognized options schema; missing fields: " + ", ".join(missing)
            ],
        }

    field_mapping = {field: available_fields[field] for field in required}
    normalized = {}
    for record in records:
        group = _normalized(record.get(field_mapping["group"]))
        name = _normalized(record.get(field_mapping["name"]))
        if group == "HYDRAULICS" and name:
            normalized[name] = record.get(field_mapping["value"])

    flow_code = _normalized(normalized.get("UNITS"))
    headloss_code = _normalized(normalized.get("HEADLOSS"))
    flow_details = FLOW_UNIT_MAP.get(flow_code)
    method_details = HEADLOSS_METHOD_MAP.get(headloss_code)

    if not flow_code:
        warnings.append("Hydraulics / UNITS was not found.")
    elif flow_details is None:
        warnings.append(f"Unknown QGISRed/EPANET flow unit code: {flow_code}")
    elif not flow_details[2]:
        warnings.append(
            f"Flow unit {flow_code} was detected but is not supported for sizing yet."
        )

    if not headloss_code:
        warnings.append("Hydraulics / HEADLOSS was not found.")
    elif method_details is None:
        warnings.append(f"Unknown headloss method code: {headloss_code}")
    elif not method_details[1]:
        warnings.append(
            f"Headloss method {headloss_code} is outside the first-version scope."
        )

    return {
        "schema_recognized": True,
        "field_mapping": field_mapping,
        "flow_units_code": flow_code,
        "flow_unit": flow_details[0] if flow_details else "",
        "unit_system": flow_details[1] if flow_details else "",
        "flow_unit_supported": flow_details[2] if flow_details else False,
        "headloss_code": headloss_code,
        "hydraulic_method": method_details[0] if method_details else "",
        "hydraulic_method_supported": method_details[1] if method_details else False,
        "warnings": warnings,
    }


def format_options_inspection(inspection: Mapping[str, Any]) -> str:
    """Format DBF metadata, validated semantics, fields, and records."""
    semantics = inspection["semantics"]
    lines = [
        "QGISRed Options DBF — read-only inspection",
        f"Path: {inspection['path']}",
        f"Network base: {inspection['network_base'] or '<not inferred>'}",
        f"Provider: {inspection['provider']}",
        f"Encoding: {inspection['encoding'] or '<provider default>'}",
        f"File size: {inspection['file_size']} bytes",
        f"Records: {inspection['feature_count']}",
        f"Read-only adapter: {'yes' if inspection['read_only'] else 'no'}",
        "",
        "Detected settings",
        f"  Schema recognized: {'yes' if semantics['schema_recognized'] else 'no'}",
        f"  Flow units: {semantics['flow_units_code'] or '<not detected>'}",
        f"  Unit system: {semantics['unit_system'] or '<not detected>'}",
        f"  Headloss: {semantics['headloss_code'] or '<not detected>'}",
        f"  Method: {semantics['hydraulic_method'] or '<not detected>'}",
        "",
        f"Fields ({len(inspection['fields'])})",
    ]
    for field in inspection["fields"]:
        lines.append(
            f"  - {field['name']} ({field['type']}; length={field['length']}; "
            f"precision={field['precision']})"
        )

    lines.extend(["", f"Records shown ({len(inspection['records'])})"])
    field_names = [field["name"] for field in inspection["fields"]]
    for index, record in enumerate(inspection["records"], start=1):
        values = "; ".join(
            f"{field_name}={_display_value(record.get(field_name))}"
            for field_name in field_names
        )
        lines.append(f"  [{index}] {values}")
    if inspection["records_truncated"]:
        lines.append(
            f"  <preview limited to {inspection['record_limit']} records>"
        )
    if semantics["warnings"]:
        lines.extend(["", "Warnings"])
        lines.extend(f"  - {warning}" for warning in semantics["warnings"])
    return "\n".join(lines)


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().upper().split())


def _json_safe(value: Any) -> Any:
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _display_value(value: Optional[Any]) -> str:
    return "<null>" if value is None else str(value)
