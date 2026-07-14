"""Minimal read-only endpoint and node-pressure attribute access for Stage 11."""

from typing import Any, Dict, Mapping, Sequence

from .layer_mapping import field_category


def read_endpoint_pressure_records(
    configuration: Mapping[str, str],
) -> Dict[str, Any]:
    """Read only mapped endpoint/pressure attributes and request no geometry."""
    from qgis.core import (
        NULL,
        QgsCoordinateTransform,
        QgsFeatureRequest,
        QgsProject,
        QgsVectorLayer,
    )

    project = QgsProject.instance()
    pipe_layer = _mapped_layer(
        project,
        configuration["pipe_layer_id"],
        configuration["pipe_layer_source"],
        "pipe",
        QgsVectorLayer,
    )
    node_layer = _mapped_layer(
        project,
        configuration["node_layer_id"],
        configuration["node_layer_source"],
        "node result",
        QgsVectorLayer,
    )
    pipe_fields = [configuration["pipe_id_field"]]
    node_fields = [
        configuration["node_id_field"],
        configuration["pressure_field"],
    ]
    _require_fields(pipe_layer, pipe_fields)
    _require_fields(node_layer, node_fields)
    pipe_records, node_records = _read_geometry_relationship(
        pipe_layer,
        node_layer,
        pipe_fields,
        node_fields,
        NULL,
        QgsFeatureRequest,
        QgsCoordinateTransform,
        project,
    )
    node_id_category = _category(node_layer, configuration["node_id_field"])
    return {
        "pipe_layer_id": pipe_layer.id(),
        "pipe_layer_name": pipe_layer.name(),
        "pipe_id_field": configuration["pipe_id_field"],
        "initial_node_id_field": "<geometry start>",
        "final_node_id_field": "<geometry end>",
        "node_layer_id": node_layer.id(),
        "node_layer_name": node_layer.name(),
        "node_id_field": configuration["node_id_field"],
        "pressure_field": configuration["pressure_field"],
        "pressure_unit": configuration["pressure_unit"],
        "pipe_crs": pipe_layer.crs().authid(),
        "endpoint_tolerance": float(configuration.get("endpoint_tolerance", 0.0)),
        "pipe_id_category": _category(pipe_layer, configuration["pipe_id_field"]),
        "initial_node_id_category": node_id_category,
        "final_node_id_category": node_id_category,
        "node_id_category": node_id_category,
        "pipe_records": pipe_records,
        "node_records": node_records,
    }


def _mapped_layer(project, layer_id, expected_source, role, vector_type):
    layer = project.mapLayer(layer_id)
    if layer is None or not isinstance(layer, vector_type):
        raise ValueError(f"The mapped {role} layer no longer exists.")
    if expected_source and _public_source(layer) != expected_source:
        raise ValueError(f"The mapped {role} layer source changed after mapping.")
    return layer


def _require_fields(layer, field_names: Sequence[str]) -> None:
    missing = [
        name for name in field_names if layer.fields().indexFromName(name) < 0
    ]
    if missing:
        raise ValueError(
            f"Mapped fields no longer exist on layer {layer.name()}: "
            + ", ".join(missing)
        )


def _category(layer, field_name):
    fields = layer.fields()
    field = fields.at(fields.indexFromName(field_name))
    return field_category(field.typeName(), field.isNumeric())


def _read_geometry_relationship(
    pipe_layer,
    node_layer,
    pipe_fields,
    node_fields,
    null_value,
    request_type,
    transform_type,
    project,
):
    pipe_request = request_type()
    pipe_request.setSubsetOfAttributes(
        [pipe_layer.fields().indexFromName(pipe_fields[0])]
    )
    pipe_records = []
    for feature in pipe_layer.getFeatures(pipe_request):
        vertices = list(feature.geometry().vertices())
        if not vertices:
            initial = final = None
        else:
            initial = (vertices[0].x(), vertices[0].y())
            final = (vertices[-1].x(), vertices[-1].y())
        value = feature[pipe_fields[0]]
        pipe_records.append(
            {
                "fid": feature.id(),
                "pipe_id": (
                    None
                    if value is None or value == null_value
                    else _plain(value)
                ),
                "initial_coordinate": initial,
                "final_coordinate": final,
            }
        )

    node_request = request_type()
    node_request.setSubsetOfAttributes(
        [node_layer.fields().indexFromName(name) for name in node_fields]
    )
    transform = None
    if node_layer.crs() != pipe_layer.crs():
        transform = transform_type(node_layer.crs(), pipe_layer.crs(), project)
    node_records = []
    for feature in node_layer.getFeatures(node_request):
        vertices = list(feature.geometry().vertices())
        coordinate = None
        if vertices:
            point = transform.transform(vertices[0]) if transform else vertices[0]
            coordinate = (point.x(), point.y())
        values = []
        for name in node_fields:
            value = feature[name]
            values.append(
                None
                if value is None or value == null_value
                else _plain(value)
            )
        node_records.append(
            {
                "fid": feature.id(),
                "node_id": values[0],
                "pressure": values[1],
                "coordinate": coordinate,
            }
        )
    return pipe_records, node_records


def _plain(value: Any) -> Any:
    return value if isinstance(value, (bool, int, float, str)) else str(value)


def _public_source(layer) -> str:
    public_source = getattr(layer, "publicSource", None)
    if not callable(public_source):
        return ""
    try:
        return public_source(True)
    except TypeError:
        return public_source()
