"""Pure validation of mapped pipe and result records."""

from collections import defaultdict
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


ValidationResult = Dict[str, Any]


def validate_mapped_data(dataset: Mapping[str, Any]) -> ValidationResult:
    """Validate IDs, record correspondence, flow, and attribute length."""
    issues: List[Dict[str, Any]] = []
    pipe_records = dataset["pipe_records"]
    result_records = dataset["result_records"]
    pipe_id_category = dataset["pipe_id_category"]
    result_id_category = dataset["result_id_category"]

    if not pipe_records:
        issues.append(
            _issue(
                "error",
                "no_pipe_records",
                "pipe_layer",
                None,
                None,
                None,
                "The pipe layer contains no records.",
            )
        )
    if not result_records:
        issues.append(
            _issue(
                "error",
                "no_result_records",
                "result_layer",
                None,
                None,
                None,
                "The result layer/table contains no records.",
            )
        )
    if pipe_id_category != result_id_category:
        issues.append(
            _issue(
                "error",
                "id_type_mismatch",
                "mapping",
                None,
                None,
                None,
                "Pipe and result ID fields have incompatible types: "
                f"{pipe_id_category} versus {result_id_category}.",
            )
        )

    pipe_index = defaultdict(list)
    result_index = defaultdict(list)
    pipe_normalized = {}
    result_normalized = {}
    result_numeric_flow = {}

    for record in pipe_records:
        normalized_id, id_error = _normalize_id(
            record["id"], pipe_id_category
        )
        pipe_normalized[record["fid"]] = normalized_id
        if id_error:
            issues.append(
                _record_issue(
                    "error",
                    id_error,
                    "pipe",
                    record,
                    dataset["pipe_id_field"],
                    "Pipe ID is null, empty, or incompatible with its field type.",
                )
            )
        else:
            pipe_index[normalized_id].append(record)

        length, length_error = _finite_number(record["length"])
        if length_error:
            issues.append(
                _record_issue(
                    "error",
                    f"invalid_length_{length_error}",
                    "pipe",
                    record,
                    dataset["length_field"],
                    "Pipe length must be a finite numeric attribute value.",
                )
            )
        elif length <= 0:
            issues.append(
                _record_issue(
                    "error",
                    "nonpositive_length",
                    "pipe",
                    record,
                    dataset["length_field"],
                    f"Pipe length must be greater than zero; received {length}.",
                )
            )

    for record in result_records:
        normalized_id, id_error = _normalize_id(
            record["id"], result_id_category
        )
        result_normalized[record["fid"]] = normalized_id
        if id_error:
            issues.append(
                _record_issue(
                    "error",
                    id_error,
                    "result",
                    record,
                    dataset["result_id_field"],
                    "Result ID is null, empty, or incompatible with its field type.",
                )
            )
        else:
            result_index[normalized_id].append(record)

        flow, flow_error = _finite_number(record["flow"])
        result_numeric_flow[record["fid"]] = flow
        if flow_error:
            issues.append(
                _record_issue(
                    "error",
                    f"invalid_flow_{flow_error}",
                    "result",
                    record,
                    dataset["flow_field"],
                    "Flow must be a finite numeric value.",
                )
            )
        elif flow < 0:
            issues.append(
                _record_issue(
                    "warning",
                    "negative_flow",
                    "result",
                    record,
                    dataset["flow_field"],
                    f"Negative flow {flow} will retain its sign in records; "
                    "later sizing will use its absolute value.",
                )
            )
        elif flow == 0:
            issues.append(
                _record_issue(
                    "warning",
                    "zero_flow",
                    "result",
                    record,
                    dataset["flow_field"],
                    "Zero flow requires an explicit sizing rule in a later stage.",
                )
            )

    for normalized_id, records in pipe_index.items():
        if len(records) > 1:
            for record in records:
                issues.append(
                    _record_issue(
                        "error",
                        "duplicate_pipe_id",
                        "pipe",
                        record,
                        dataset["pipe_id_field"],
                        f"Pipe ID {normalized_id!r} is duplicated.",
                    )
                )

    for normalized_id, records in result_index.items():
        if len(records) <= 1:
            continue
        flows = {
            result_numeric_flow[record["fid"]]
            for record in records
            if result_numeric_flow[record["fid"]] is not None
        }
        conflicting = len(flows) > 1
        severity = "error" if conflicting else "warning"
        code = (
            "duplicate_result_id_conflicting"
            if conflicting
            else "duplicate_result_id_equivalent"
        )
        message = (
            f"Result ID {normalized_id!r} has conflicting flow values."
            if conflicting
            else f"Result ID {normalized_id!r} is repeated with equivalent flow."
        )
        for record in records:
            issues.append(
                _record_issue(
                    severity,
                    code,
                    "result",
                    record,
                    dataset["result_id_field"],
                    message,
                )
            )

    pipe_ids = set(pipe_index)
    result_ids = set(result_index)
    pipe_without_result = pipe_ids - result_ids
    result_without_pipe = result_ids - pipe_ids
    for normalized_id in sorted(pipe_without_result):
        for record in pipe_index[normalized_id]:
            issues.append(
                _record_issue(
                    "error",
                    "pipe_without_result",
                    "pipe",
                    record,
                    dataset["pipe_id_field"],
                    f"Pipe ID {normalized_id!r} has no corresponding result.",
                )
            )
    for normalized_id in sorted(result_without_pipe):
        for record in result_index[normalized_id]:
            issues.append(
                _record_issue(
                    "warning",
                    "result_without_pipe",
                    "result",
                    record,
                    dataset["result_id_field"],
                    f"Result ID {normalized_id!r} has no corresponding pipe.",
                )
            )

    issues.sort(key=_issue_sort_key)
    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    pipe_problem_fids = sorted(
        {
            issue["fid"]
            for issue in issues
            if issue["entity"] == "pipe" and issue["fid"] is not None
        }
    )
    result_problem_fids = sorted(
        {
            issue["fid"]
            for issue in issues
            if issue["entity"] == "result" and issue["fid"] is not None
        }
    )
    return {
        "valid_for_sizing": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "pipe_problem_fids": pipe_problem_fids,
        "result_problem_fids": result_problem_fids,
        "summary": {
            "pipe_records": len(pipe_records),
            "result_records": len(result_records),
            "valid_pipe_ids": len(pipe_ids),
            "valid_result_ids": len(result_ids),
            "matched_ids": len(pipe_ids & result_ids),
            "pipes_without_result": len(pipe_without_result),
            "results_without_pipe": len(result_without_pipe),
        },
    }


def format_validation_report(
    dataset: Mapping[str, Any],
    result: Mapping[str, Any],
    issue_limit: int = 500,
) -> str:
    """Create a deterministic, readable Stage 5 validation report."""
    summary = result["summary"]
    if result["valid_for_sizing"] and result["warning_count"]:
        status = "PASS WITH WARNINGS"
    elif result["valid_for_sizing"]:
        status = "PASS"
    else:
        status = "FAIL"
    lines = [
        "HydroSizer Data Validation — Stage 5",
        "Mode: read-only; no attributes or geometries were changed",
        "",
        "Mapping",
        f"  Pipe layer: {dataset['pipe_layer_name']}",
        f"  Pipe ID: {dataset['pipe_id_field']}",
        f"  Length attribute: {dataset['length_field']}",
        f"  Result layer/table: {dataset['result_layer_name']}",
        f"  Result ID: {dataset['result_id_field']}",
        f"  Flow: {dataset['flow_field']}",
        "",
        "Summary",
        f"  Status: {status}",
        f"  Errors: {result['error_count']}",
        f"  Warnings: {result['warning_count']}",
        f"  Pipe records: {summary['pipe_records']}",
        f"  Result records: {summary['result_records']}",
        f"  Valid pipe IDs: {summary['valid_pipe_ids']}",
        f"  Valid result IDs: {summary['valid_result_ids']}",
        f"  Matched IDs: {summary['matched_ids']}",
        f"  Pipes without result: {summary['pipes_without_result']}",
        f"  Results without pipe: {summary['results_without_pipe']}",
        "",
        f"Issues ({len(result['issues'])})",
    ]
    if not result["issues"]:
        lines.append("  <none>")
    for issue in result["issues"][:issue_limit]:
        location = issue["entity"]
        if issue["fid"] is not None:
            location += f" fid={issue['fid']}"
        if issue["raw_id"] is not None:
            location += f" id={issue['raw_id']!r}"
        lines.append(
            f"  [{issue['severity'].upper()}] {issue['code']} — "
            f"{location}: {issue['message']}"
        )
    if len(result["issues"]) > issue_limit:
        lines.append(
            f"  <report limited to {issue_limit} of {len(result['issues'])} issues>"
        )
    return "\n".join(lines)


def _normalize_id(value: Any, category: str) -> Tuple[Optional[str], str]:
    if value is None:
        return None, "null_id"
    if category == "text":
        normalized = str(value).strip()
        return (normalized, "") if normalized else (None, "empty_id")
    if category == "integer":
        if isinstance(value, bool):
            return None, "invalid_id_type"
        if isinstance(value, int):
            return str(value), ""
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return str(int(value)), ""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and stripped.lstrip("+-").isdigit():
                return str(int(stripped)), ""
        return None, "invalid_id_type"
    return None, "invalid_id_type"


def _finite_number(value: Any) -> Tuple[Optional[float], str]:
    if value is None:
        return None, "null"
    if isinstance(value, bool):
        return None, "nonnumeric"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "nonnumeric"
    if not math.isfinite(number):
        return None, "nonfinite"
    return number, ""


def _record_issue(
    severity: str,
    code: str,
    entity: str,
    record: Mapping[str, Any],
    field: str,
    message: str,
) -> Dict[str, Any]:
    id_codes = {
        "null_id",
        "empty_id",
        "invalid_id_type",
        "duplicate_pipe_id",
        "duplicate_result_id_conflicting",
        "duplicate_result_id_equivalent",
        "pipe_without_result",
        "result_without_pipe",
    }
    if code in id_codes:
        value = record["id"]
    elif entity == "pipe":
        value = record.get("length")
    else:
        value = record.get("flow")
    return _issue(
        severity,
        code,
        entity,
        record["fid"],
        record["id"],
        value,
        message,
        field,
    )


def _issue(
    severity: str,
    code: str,
    entity: str,
    fid: Optional[int],
    raw_id: Any,
    value: Any,
    message: str,
    field: str = "",
) -> Dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "entity": entity,
        "fid": fid,
        "raw_id": raw_id,
        "field": field,
        "value": value,
        "message": message,
    }


def _issue_sort_key(issue: Mapping[str, Any]):
    return (
        0 if issue["severity"] == "error" else 1,
        issue["entity"],
        issue["fid"] if issue["fid"] is not None else -1,
        issue["code"],
    )
