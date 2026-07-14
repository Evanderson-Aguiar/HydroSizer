"""QGIS adapter for revalidated, undoable Stage 14 attribute changes."""

import math
from typing import Any, Callable, Mapping, Sequence

try:
    from ..core.apply_plan import revalidate_apply_plan
except ImportError:  # Standalone test discovery from the plugin directory.
    from core.apply_plan import revalidate_apply_plan


def read_apply_records(
    configuration: Mapping[str, Any],
    pipe_fids: Sequence[int],
) -> list:
    """Read only current IDs and mapped target values for explicit FIDs."""
    from qgis.core import NULL, Qgis, QgsFeatureRequest, QgsProject, QgsVectorLayer

    layer = _require_layer(configuration, QgsProject, QgsVectorLayer)
    field_names = [configuration["pipe_id_field"]] + list(
        configuration["target_fields"]
    )
    _require_fields(layer, field_names)
    indices = [layer.fields().indexFromName(name) for name in field_names]
    request = QgsFeatureRequest()
    request.setFilterFids([int(fid) for fid in pipe_fids])
    request.setSubsetOfAttributes(indices)
    no_geometry = getattr(QgsFeatureRequest, "NoGeometry", None)
    if no_geometry is None:
        no_geometry = Qgis.FeatureRequestFlag.NoGeometry
    request.setFlags(no_geometry)
    records = []
    for feature in layer.getFeatures(request):
        values = {}
        for field_name in configuration["target_fields"]:
            value = feature[field_name]
            values[field_name] = (
                None if value is None or value == NULL else _plain_value(value)
            )
        identifier = feature[configuration["pipe_id_field"]]
        records.append(
            {
                "fid": feature.id(),
                "id": None if identifier is None or identifier == NULL else identifier,
                "values": values,
            }
        )
    return records


def apply_change_plan(
    configuration: Mapping[str, Any],
    plan: Mapping[str, Any],
    audit_callback: Callable[[], Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Revalidate, edit one undo command, and rollback on any critical failure."""
    from qgis.core import QgsProject, QgsVectorLayer

    layer = _require_layer(configuration, QgsProject, QgsVectorLayer)
    _require_fields(
        layer,
        [configuration["pipe_id_field"]] + list(configuration["target_fields"]),
    )
    if layer.readOnly():
        raise ValueError(f"layer {layer.name()} is read-only")
    current = read_apply_records(
        configuration,
        [row["pipe_fid"] for row in plan["rows"]],
    )
    revalidate_apply_plan(plan, current)
    _validate_new_values(layer, plan)

    started_session = False
    command_started = False
    try:
        if not layer.isEditable():
            if not layer.startEditing():
                raise ValueError(f"layer {layer.name()} could not start editing")
            started_session = True
        layer.beginEditCommand("HydroSizer safe pipe sizing apply")
        command_started = True
        changed_attributes = 0
        changed_features = 0
        for row in plan["rows"]:
            row_changed = False
            for field_name, change in row["changes"].items():
                if not change["changed"]:
                    continue
                index = layer.fields().indexFromName(field_name)
                value = _coerce_for_field(layer.fields().at(index), change["new"])
                if not layer.changeAttributeValue(
                    int(row["pipe_fid"]),
                    index,
                    value,
                    change["old"],
                ):
                    raise RuntimeError(
                        f"QGIS rejected {field_name} for pipe {row['pipe_id']}"
                    )
                changed_attributes += 1
                row_changed = True
            if row_changed:
                changed_features += 1
        audit_result = audit_callback()
        layer.endEditCommand()
        command_started = False
        return {
            "changed_features": changed_features,
            "changed_attributes": changed_attributes,
            "edit_session_started": started_session,
            "pending_save": True,
            "audit": audit_result,
        }
    except Exception:
        if command_started:
            layer.destroyEditCommand()
        if started_session and layer.isEditable():
            layer.rollBack()
        raise


def _require_layer(configuration, project_type, vector_type):
    layer = project_type.instance().mapLayer(configuration["layer_id"])
    if layer is None or not isinstance(layer, vector_type):
        raise ValueError("mapped pipe layer no longer exists")
    current_source = _public_source(layer)
    expected_source = configuration.get("layer_source", "")
    if expected_source and current_source != expected_source:
        raise ValueError("mapped pipe layer source changed after preview")
    return layer


def _require_fields(layer, field_names):
    missing = [name for name in field_names if layer.fields().indexFromName(name) < 0]
    if missing:
        raise ValueError("destination fields no longer exist: " + ", ".join(missing))


def _validate_new_values(layer, plan):
    for row in plan["rows"]:
        for field_name, change in row["changes"].items():
            if change["changed"]:
                index = layer.fields().indexFromName(field_name)
                _coerce_for_field(layer.fields().at(index), change["new"])


def _coerce_for_field(field, value):
    if value is None:
        return None
    if field.isNumeric():
        if isinstance(value, bool):
            raise ValueError(f"field {field.name()} requires a numeric value")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"field {field.name()} received a non-finite value")
        type_name = field.typeName().casefold()
        if "int" in type_name or "long" in type_name:
            if not number.is_integer():
                raise ValueError(
                    f"field {field.name()} is integer but value {number} is not"
                )
            return int(number)
        return number
    text = str(value)
    if field.length() > 0 and len(text) > field.length():
        raise ValueError(
            f"value for field {field.name()} exceeds its length {field.length()}"
        )
    return text


def _plain_value(value: Any) -> Any:
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _public_source(layer) -> str:
    public_source = getattr(layer, "publicSource", None)
    if not callable(public_source):
        return ""
    try:
        return public_source(True)
    except TypeError:
        return public_source()
