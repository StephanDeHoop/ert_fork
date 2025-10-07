# docs/_ext/render_schema.py
from __future__ import annotations

import json
import re
from typing import Any


def _slug(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "section"


def _fmt_default(value: Any) -> str:
    if value is None:
        return "`null`"
    try:
        s = json.dumps(value, ensure_ascii=False)
    except Exception:
        s = str(value)
    return f"`{s}`"


def _type_label(node: dict[str, Any]) -> str:
    # Concise type label with links for $ref
    if "$ref" in node:
        ref = node["$ref"]
        m = re.search(r"#/(?:\$defs|definitions)/(.+)", ref)
        if m:
            ref_name = m.group(1)
            return f"{ref_name})"
        return f"`$ref` to `{ref}`"

    if "enum" in node:
        return "enum"

    if "type" in node:
        t = node["type"]
        if isinstance(t, list):
            return " | ".join(f"`{x}`" for x in t)
        return f"`{t}`"

    for comb in ("anyOf", "oneOf", "allOf"):
        if comb in node:
            parts = []
            for sub in node[comb]:
                parts.append(_type_label(sub))
            return f"{comb}(" + ", ".join(parts) + ")"

    if "properties" in node or "additionalProperties" in node:
        return "`object`"
    if "items" in node:
        return "`array`"

    return "`unknown`"


def _render_constraints(node: dict[str, Any]) -> list[str]:
    lines = []
    # Add common JSON Schema constraints if present
    for key in [
        "title",
        "format",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "exclusiveMinimum",
        "maximum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
        "const",
    ]:
        if key in node:
            val = node[key]
            if isinstance(val, (dict, list)):
                val_str = f"`{json.dumps(val, ensure_ascii=False)}`"
            else:
                val_str = (
                    f"`{val}`" if not isinstance(val, bool) else f"`{str(val).lower()}`"
                )
            if key == "title":
                # Present title as plain text (not code) for readability
                val_str = str(val)
            lines.append(f"- **{key}:** {val_str}")
    return lines


def _definition_names(schema: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # Pydantic v2 uses $defs; v1 uses definitions
    defs = schema.get("$defs")
    name = "$defs"
    if defs is None:
        defs = schema.get("definitions")
        name = "definitions"
    return name, defs or {}


def render_schema_markdown(
    schema: dict[str, Any],
    title: str | None = None,
    max_heading_level: int = 6,
) -> str:
    """
    Render a JSON Schema (from Pydantic model_json_schema) to MyST Markdown
    with headings and anchors. Descriptions are injected verbatim so fenced
    code blocks (```yaml / ```bash / ```python) render as-is in MyST.
    """
    title = title or schema.get("title") or "Everest Configuration Keyword Reference"

    out: list[str] = []
    out.append("(_cha_everest_keyword_reference)=\n")
    out.append(f"# {title}")

    # If the top-level schema has a description, render it verbatim
    if schema.get("description"):
        # Strip only leading blank lines to avoid accidental extra spacing
        desc = str(schema["description"]).lstrip("\n")
        out.append(f"{desc}\n")

    props: dict[str, Any] = schema.get("properties", {}) or {}
    required_set = set(schema.get("required", []) or [])

    def render_object(
        node: dict[str, Any],
        path: list[str],
        level: int,
        header_name: str | None = None,
    ):
        nonlocal out
        level = min(level, max_heading_level)

        # Visible section title
        name = header_name or (path[-1] if path else (schema.get("title") or "Root"))
        hashes = "#" * min(level, 6)

        out.append(f"{hashes} {name}\n")

        # Meta block
        meta_lines: list[str] = []
        meta_lines.append(f"- **type:** {_type_label(node)}")

        if "default" in node:
            meta_lines.append(f"- **default:** {_fmt_default(node['default'])}")
        if node.get("deprecated"):
            meta_lines.append("- **deprecated:** `true`")

        meta_lines.extend(_render_constraints(node))

        if "enum" in node:
            vals = node["enum"]
            items = ", ".join(f"`{json.dumps(v, ensure_ascii=False)}`" for v in vals)
            meta_lines.append(f"- **enum:** {items}")

        if meta_lines:
            out.extend(meta_lines)
            out.append("")

        # Description: verbatim (supporting ```yaml/```bash/```python/…)
        if node.get("description"):
            desc = str(node["description"]).lstrip("\n")
            out.append(desc)
            out.append("")

        # Combinators: show options succinctly (linking when possible)
        for comb in ("allOf", "anyOf", "oneOf"):
            if comb in node:
                out.append(f"**{comb}:**")
                out.append("")
                for i, sub in enumerate(node[comb], start=1):
                    out.append(f"- Option {i}: {_type_label(sub)}")
                out.append("")

        # Arrays
        if node.get("type") == "array" or "items" in node:
            items = node.get("items")
            if items:
                out.append("**Items:** " + _type_label(items))
                out.append("")
                # If array items is an inline object, descend
                if isinstance(items, dict) and (
                    "properties" in items or items.get("type") == "object"
                ):
                    render_object(
                        items,
                        path + ["items"],
                        level + 1,
                        required=set(items.get("required", [])),
                    )

        # Objects
        if isinstance(node.get("properties"), dict):
            props = node["properties"]
            req = set(node.get("required", []) or [])
            for pname, pnode in props.items():
                child_path = path + [pname]
                label = f"{pname} "
                label += " (required)" if pname in req else " (optional)"
                render_object(
                    pnode, child_path, level + 1, required=req, header_name=label
                )

        # Map-like schemas
        if node.get("additionalProperties") not in (None, False):
            ap = node["additionalProperties"]
            ap_label = "additionalProperties"
            if ap is True:
                out.append("**additionalProperties:** `true`")
                out.append("")
            elif isinstance(ap, dict):
                render_object(
                    ap, path + ["additionalProperties"], level + 1, header_name=ap_label
                )

    # Render the main object wrapper to ensure consistent structure
    render_object(
        {
            "type": "object",
            "properties": props,
            "required": list(required_set),
            "description": schema.get("description"),
        },
        path=[],
        level=1,
        required=required_set,
        header_name=schema.get("title") or "Configuration",
    )

    # Definitions section for $ref targets
    _, defs = _definition_names(schema)
    if defs:
        out.append("")
        out.append("## Definitions ")
        out.append("")
        for def_name, def_node in defs.items():
            def_anchor = f"def-{_slug(def_name)}"
            render_object(def_node, [def_anchor], level=3, header_name=def_name)

    return "\n".join(out)
