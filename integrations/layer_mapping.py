"""Read-only layer inventory and mapping suggestions for Stage 4."""

from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence
import unicodedata


LayerInfo = Dict[str, Any]
MappingSuggestion = Dict[str, str]


def collect_layer_mapping_inventory() -> List[LayerInfo]:
    """Describe loaded vector layers and fields without reading features."""
    from qgis.core import Qgis, QgsProject, QgsVectorLayer, QgsWkbTypes

    line_geometry_values = {getattr(QgsWkbTypes, "LineGeometry", None)}
    geometry_type = getattr(Qgis, "GeometryType", None)
    if geometry_type is not None:
        line_geometry_values.add(getattr(geometry_type, "Line", None))

    inventory = []
    for layer in QgsProject.instance().mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        fields = []
        for field in layer.fields():
            category = field_category(field.typeName(), field.isNumeric())
            fields.append(
                {
                    "name": field.name(),
                    "type": field.typeName(),
                    "category": category,
                    "numeric": field.isNumeric(),
                }
            )
        is_spatial = layer.isSpatial()
        inventory.append(
            {
                "id": layer.id(),
                "name": layer.name(),
                "source": _public_source(layer),
                "provider": layer.providerType(),
                "is_spatial": is_spatial,
                "is_line": (
                    is_spatial and layer.geometryType() in line_geometry_values
                ),
                "fields": fields,
            }
        )
    return sorted(
        inventory,
        key=lambda layer: (layer["name"].casefold(), layer["id"]),
    )


def suggest_layer_mapping(inventory: Sequence[LayerInfo]) -> MappingSuggestion:
    """Suggest a fully reviewable mapping from names and field definitions."""
    pipe_candidates = [layer for layer in inventory if layer["is_line"]]
    pipe_layer = _best_layer(pipe_candidates, _pipe_layer_score)

    result_candidates = [
        layer
        for layer in inventory
        if any(field["numeric"] for field in layer["fields"])
    ]
    if pipe_layer is not None:
        alternatives = [
            layer for layer in result_candidates if layer["id"] != pipe_layer["id"]
        ]
        if alternatives:
            result_candidates = alternatives
    result_layer = _best_layer(result_candidates, _result_layer_score)

    pipe_id = _suggest_field(pipe_layer, "id")
    length = _suggest_field(pipe_layer, "length")
    pipe_id_category = _field_category_by_name(pipe_layer, pipe_id)
    result_id = _suggest_field(
        result_layer, "id", required_category=pipe_id_category
    )
    flow = _suggest_field(result_layer, "flow")
    return {
        "pipe_layer_id": pipe_layer["id"] if pipe_layer else "",
        "pipe_id_field": pipe_id,
        "length_field": length,
        "result_layer_id": result_layer["id"] if result_layer else "",
        "result_id_field": result_id,
        "flow_field": flow,
    }


def compatible_fields(
    layer: Optional[Mapping[str, Any]],
    role: str,
    id_category: str = "",
) -> List[Mapping[str, Any]]:
    """Return fields compatible with a mapping role."""
    if layer is None:
        return []
    if role in {"length", "flow"}:
        return [field for field in layer["fields"] if field["numeric"]]
    if role in {"pipe_id", "result_id"}:
        fields = [
            field
            for field in layer["fields"]
            if field["category"] in {"text", "integer"}
        ]
        if role == "result_id" and id_category:
            fields = [field for field in fields if field["category"] == id_category]
        return fields
    raise ValueError(f"Unknown mapping role: {role}")


def mapping_display_name(layer: Mapping[str, Any]) -> str:
    """Return an unambiguous layer label for a combo box."""
    layer_kind = "line" if layer["is_line"] else (
        "vector" if layer["is_spatial"] else "table"
    )
    return f"{layer['name']} — {layer_kind} — {layer['provider']}"


def _pipe_layer_score(layer: Mapping[str, Any]) -> int:
    name = _normalized_identifier(layer["name"])
    source_stem = _source_stem(layer["source"])
    field_names = {_normalized_identifier(field["name"]) for field in layer["fields"]}
    score = 20
    if name in {"pipes", "pipe", "tubulacoes", "tubulacao"}:
        score += 120
    if source_stem.endswith("_pipes"):
        score += 100
    if "length" in field_names or "comprimento" in field_names:
        score += 30
    if "diameter" in field_names or "dn" in field_names:
        score += 10
    return score


def _result_layer_score(layer: Mapping[str, Any]) -> int:
    name = _normalized_identifier(layer["name"])
    source = layer["source"].replace("\\", "/").casefold()
    field_names = {_normalized_identifier(field["name"]) for field in layer["fields"]}
    score = 0
    if "/results/" in source:
        score += 100
    if "flow" in field_names or "vazao" in field_names:
        score += 100
    if "flow" in name or "vazao" in name:
        score += 70
    if "link" in name:
        score += 20
    return score


def _best_layer(layers, score_function):
    if not layers:
        return None
    return sorted(
        layers,
        key=lambda layer: (
            -score_function(layer),
            layer["name"].casefold(),
            layer["id"],
        ),
    )[0]


def _suggest_field(
    layer: Optional[Mapping[str, Any]],
    role: str,
    required_category: str = "",
) -> str:
    if layer is None:
        return ""
    role_for_filter = "result_id" if role == "id" and required_category else (
        "pipe_id" if role == "id" else role
    )
    fields = compatible_fields(layer, role_for_filter, required_category)
    preferences = {
        "id": ["id", "pipe_id", "pipeid", "link_id", "linkid", "dc_id"],
        "length": ["length", "comprimento", "len"],
        "flow": ["flow", "vazao", "flow_unsig", "flow_sig"],
    }[role]
    normalized_fields = {
        _normalized_identifier(field["name"]): field["name"] for field in fields
    }
    for preferred in preferences:
        if preferred in normalized_fields:
            return normalized_fields[preferred]
    return ""


def _field_category_by_name(
    layer: Optional[Mapping[str, Any]], field_name: str
) -> str:
    if layer is None or not field_name:
        return ""
    for field in layer["fields"]:
        if field["name"] == field_name:
            return field["category"]
    return ""


def field_category(type_name: str, numeric: bool) -> str:
    """Classify a provider field for mapping and ID compatibility."""
    normalized = type_name.casefold()
    if numeric:
        if "int" in normalized or "long" in normalized:
            return "integer"
        return "numeric"
    if any(token in normalized for token in ("string", "text", "char")):
        return "text"
    return "other"


def _public_source(layer) -> str:
    public_source = getattr(layer, "publicSource", None)
    if not callable(public_source):
        return ""
    try:
        return public_source(True)
    except TypeError:
        return public_source()


def _normalized_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9_]+", "", without_accents.casefold())


def _source_stem(source: str) -> str:
    raw_path = source.split("|", 1)[0].replace("\\", "/")
    return Path(raw_path).stem.casefold()
