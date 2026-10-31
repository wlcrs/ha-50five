"""Shared helpers to censor sensitive values in debug logs and diagnostics."""

from __future__ import annotations

from typing import Annotated, Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from .models import ToMask, ToRedact

MASKED_KEYS = {
    "email",
    "getcustomerbyidid",
    "getchargestationbyidid",
    "chargestationid",
    "channelid",
    "card",
}
REDACTED_KEYS = {
    "password",
    "token",
    "authorization",
}


def _normalize_key(key: str) -> str:
    """Normalize a dict key for lookup, tolerating camelCase and snake_case."""
    return key.lower().replace("_", "")


def _is_redacted_type(annotation: Any) -> bool:
    """Return whether an annotation contains the ToRedact marker."""
    if get_origin(annotation) is Annotated:
        annotated_args = get_args(annotation)
        if any(metadata is ToRedact for metadata in annotated_args[1:]):
            return True
    return any(_is_redacted_type(arg) for arg in get_args(annotation))


def _is_masked_type(annotation: Any) -> bool:
    """Return whether an annotation contains the ToMask marker."""
    if get_origin(annotation) is Annotated:
        annotated_args = get_args(annotation)
        if any(metadata is ToMask for metadata in annotated_args[1:]):
            return True
    return any(_is_masked_type(arg) for arg in get_args(annotation))


def _nested_model_type(annotation: Any) -> type[BaseModel] | None:
    """Find a nested Pydantic model inside a field or collection annotation."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        nested_type = _nested_model_type(arg)
        if nested_type is not None:
            return nested_type
    return None


def _model_field(model: type[BaseModel] | None, key: str) -> tuple[str, Any] | None:
    """Find the response-model field matching a GraphQL key or Python name."""
    if model is None:
        return None
    key_norm = _normalize_key(key)
    for field_name, model_field in model.model_fields.items():
        if key_norm in {
            _normalize_key(field_name),
            _normalize_key(model_field.alias or field_name),
        }:
            return field_name, model_field
    return None


def mask_value(value: Any) -> str:
    """Mask a sensitive value, keeping first/last 2 chars for differentiation."""
    value = str(value)
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def censor(
    data: Any,
    *,
    response_model: type[BaseModel] | None = None,
) -> Any:
    """Recursively censor sensitive values using their model schema or key."""
    if isinstance(data, BaseModel):
        censored: dict[str, Any] = {}
        annotations = get_type_hints(type(data), include_extras=True)
        for field_name in type(data).model_fields:
            value = getattr(data, field_name)
            key_norm = _normalize_key(field_name)
            if _is_redacted_type(annotations.get(field_name)):
                censored[field_name] = "<redacted>"
            elif _is_masked_type(annotations.get(field_name)):
                censored[field_name] = (
                    mask_value(value) if value is not None else None
                )
            else:
                censored[field_name] = censor(value)
        return censored

    if isinstance(data, dict):
        censored: dict[str, Any] = {}
        annotations = (
            get_type_hints(response_model, include_extras=True)
            if response_model is not None
            else {}
        )
        for key, value in data.items():
            key_norm = _normalize_key(str(key))
            matched_field = _model_field(response_model, str(key))
            annotation = (
                annotations.get(matched_field[0]) if matched_field else None
            )
            if _is_redacted_type(annotation) or key_norm in REDACTED_KEYS:
                censored[key] = "<redacted>"
            elif _is_masked_type(annotation) or key_norm in MASKED_KEYS:
                censored[key] = mask_value(value) if value is not None else None
            else:
                censored[key] = censor(
                    value, response_model=_nested_model_type(annotation)
                )
        return censored

    if isinstance(data, list):
        return [censor(item, response_model=response_model) for item in data]

    return data
