"""Minimal read-only attribute access for mapped Stage 5 fields."""

from typing import Any, Dict, Mapping, Sequence

from .layer_mapping import field_category


def read_mapped_records(configuration: Mapping[str, str]) -> Dict[str, Any]:
    """Read only the six mapped attributes, explicitly excluding geometry."""
    from qgis.core import NULL, Qgis, QgsFeatureRequest, QgsProject, QgsVectorLayer

    project = QgsProject.instance()
    pipe_layer = _mapped_vector_layer(
        project,
        configuration["pipe_layer_id"],
        configuration["pipe_layer_source"],
        "pipe",
        QgsVectorLayer,
    )
    result_layer = _mapped_vector_layer(
        project,
        configuration["result_layer_id"],
        configuration["result_layer_source"],
        "result",
        QgsVectorLayer,
    )
    pipe_fields = [configuration["pipe_id_field"], configuration["length_field"]]
    result_fields = [configuration["result_id_field"], configuration["flow_field"]]
    _require_fields(pipe_layer, pipe_fields)
    _require_fields(result_layer, result_fields)

    pipe_records = _read_attributes(
        pipe_layer,
        pipe_fields,
        ("id", "length"),
        NULL,
        Qgis,
        QgsFeatureRequest,
    )
    result_records = _read_attributes(
        result_layer,
        result_fields,
        ("id", "flow"),
        NULL,
        Qgis,
        QgsFeatureRequest,
    )
    pipe_field_definitions = pipe_layer.fields()
    result_field_definitions = result_layer.fields()
    pipe_id_definition = pipe_field_definitions.at(
        pipe_field_definitions.indexFromName(configuration["pipe_id_field"])
    )
    result_id_definition = result_field_definitions.at(
        result_field_definitions.indexFromName(configuration["result_id_field"])
    )
    return {
        "pipe_layer_id": pipe_layer.id(),
        "pipe_layer_name": pipe_layer.name(),
        "pipe_id_field": configuration["pipe_id_field"],
        "length_field": configuration["length_field"],
        "result_layer_id": result_layer.id(),
        "result_layer_name": result_layer.name(),
        "result_id_field": configuration["result_id_field"],
        "flow_field": configuration["flow_field"],
        "pipe_id_category": field_category(
            pipe_id_definition.typeName(), pipe_id_definition.isNumeric()
        ),
        "result_id_category": field_category(
            result_id_definition.typeName(), result_id_definition.isNumeric()
        ),
        "pipe_records": pipe_records,
        "result_records": result_records,
    }


def _mapped_vector_layer(project, layer_id, expected_source, role, vector_type):
    layer = project.mapLayer(layer_id)
    if layer is None or not isinstance(layer, vector_type):
        raise ValueError(f"The mapped {role} layer no longer exists.")
    current_source = _public_source(layer)
    if expected_source and current_source != expected_source:
        raise ValueError(f"The mapped {role} layer source changed after mapping.")
    return layer


def _require_fields(layer, field_names: Sequence[str]) -> None:
    missing = [
        field_name
        for field_name in field_names
        if layer.fields().indexFromName(field_name) < 0
    ]
    if missing:
        raise ValueError(
            f"Mapped fields no longer exist on layer {layer.name()}: "
            + ", ".join(missing)
        )


def _read_attributes(
    layer,
    field_names,
    output_names,
    null_value,
    qgis_type,
    request_type,
):
    indices = [layer.fields().indexFromName(name) for name in field_names]
    request = request_type()
    request.setSubsetOfAttributes(indices)
    no_geometry = getattr(request_type, "NoGeometry", None)
    if no_geometry is None:
        no_geometry = qgis_type.FeatureRequestFlag.NoGeometry
    request.setFlags(no_geometry)

    records = []
    for feature in layer.getFeatures(request):
        record = {"fid": feature.id()}
        for field_name, output_name in zip(field_names, output_names):
            value = feature[field_name]
            record[output_name] = (
                None if value is None or value == null_value else _plain_value(value)
            )
        records.append(record)
    return records


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
