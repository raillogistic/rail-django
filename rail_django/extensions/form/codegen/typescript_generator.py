"""
TypeScript type generation for Form API.
"""

from __future__ import annotations

from typing import Any, Iterable


TYPE_MAP = {
    "TEXT": "string",
    "TEXTAREA": "string",
    "EMAIL": "string",
    "PASSWORD": "string",
    "URL": "string",
    "PHONE": "string",
    "SLUG": "string",
    "UUID": "string",
    "RICH_TEXT": "string",
    "COLOR": "string",
    "NUMBER": "number",
    "DECIMAL": "number",
    "BOOLEAN": "boolean",
    "SWITCH": "boolean",
    "CHECKBOX": "boolean",
    "DATE": "string",
    "TIME": "string",
    "DATETIME": "string",
    "FILE": "File | string | null",
    "IMAGE": "File | string | null",
    "JSON": "Record<string, unknown>",
    "SELECT": "string",
    "RADIO": "string",
    "MULTISELECT": "string[]",
    "CUSTOM": "unknown",
    "HIDDEN": "unknown",
}


def _ts_type(field: dict[str, Any]) -> str:
    input_type = str(field.get("input_type") or "TEXT")
    return TYPE_MAP.get(input_type, "unknown")


def generate_typescript_definitions(configs: Iterable[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("export type RelationInput = {")
    lines.append("  connect?: string[];")
    lines.append("  create?: Record<string, unknown>[];")
    lines.append("  update?: { id: string; values: Record<string, unknown> }[];")
    lines.append("  disconnect?: string[];")
    lines.append("  delete?: string[];")
    lines.append("  set?: string[];")
    lines.append("  clear?: boolean;")
    lines.append("};")
    lines.append("")

    for config in configs:
        model_name = str(config.get("model") or "Model")
        fields = config.get("fields") or []
        relations = config.get("relations") or []

        lines.append(f"export interface {model_name} {{")
        for field in fields:
            name = field.get("name") or field.get("field_name")
            if not name:
                continue
            ts_type = _ts_type(field)
            optional = "?" if not field.get("required", False) else ""
            lines.append(f"  {name}{optional}: {ts_type};")
        for rel in relations:
            rel_name = rel.get("name") or rel.get("field_name")
            if not rel_name:
                continue
            is_to_many = bool(rel.get("is_to_many"))
            lines.append(
                f"  {rel_name}?: {'RelationInput[]' if is_to_many else 'RelationInput'};"
            )
        lines.append("}")
        lines.append("")

        lines.append(f"export interface {model_name}Input {{")
        for field in fields:
            name = field.get("name") or field.get("field_name")
            if not name:
                continue
            ts_type = _ts_type(field)
            lines.append(f"  {name}?: {ts_type};")
        for rel in relations:
            rel_name = rel.get("name") or rel.get("field_name")
            if not rel_name:
                continue
            is_to_many = bool(rel.get("is_to_many"))
            lines.append(
                f"  {rel_name}?: {'RelationInput[]' if is_to_many else 'RelationInput'};"
            )
        lines.append("}")
        lines.append("")

    return "\n".join(lines)
