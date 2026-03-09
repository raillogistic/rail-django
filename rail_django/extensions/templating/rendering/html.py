"""
HTML rendering utilities for PDF templating.

This module provides functions for rendering Django templates to HTML
and building CSS style blocks for PDF generation.
"""

import html
import re
from typing import Any, Iterable, Optional

from django.template import loader

from ..config import _normalize_page_stamps, _normalize_watermark, _resolve_postprocess_config


def _render_template(template_path: Optional[str], context: dict[str, Any]) -> str:
    """
    Render a template path with context. Returns an empty string when no template is provided.

    Args:
        template_path: Path relative to Django templates directories or absolute path.
        context: Context to render.

    Returns:
        Rendered HTML string.
    """
    if not template_path:
        return ""
    template = loader.get_template(template_path)
    return template.render(context)


def _normalize_html_fragment(fragment: str) -> tuple[str, list[str]]:
    """
    Extract body markup and inline CSS from a possibly full HTML document fragment.

    This lets wrapper-generated CSS remain the final authority for page geometry
    while still preserving user-defined component styling.
    """
    raw = str(fragment or "")
    css_chunks = [
        match.strip()
        for match in re.findall(
            r"<style\b[^>]*>(.*?)</style>",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match.strip()
    ]
    normalized = re.sub(
        r"<style\b[^>]*>.*?</style>",
        "",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_match = re.search(
        r"<body\b[^>]*>(.*?)</body>",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if body_match:
        normalized = body_match.group(1)
    normalized = re.sub(
        r"</?(?:html|head|body|title|meta|link)\b[^>]*>",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.strip(), css_chunks


def _build_style_block(
    config: dict[str, Any], *, extra_css_chunks: Optional[Iterable[str]] = None
) -> str:
    """
    Convert style configuration into a CSS block usable by WeasyPrint.

    Args:
        config: Style configuration merging defaults and overrides.
        extra_css_chunks: Optional list of extra CSS fragments to append.

    Returns:
        CSS string.
    """
    page_size = config.get("page_size", "A4")
    orientation = config.get("orientation", "portrait")
    margin = config.get("margin", "20mm")
    padding = config.get("padding", "12mm")
    font_family = config.get("font_family", "Arial, sans-serif")
    font_size = config.get("font_size", "12pt")
    text_color = config.get("text_color", "#222222")
    background_color = config.get("background_color", "#ffffff")
    content_spacing = config.get("content_spacing", "8mm")
    extra_css = config.get("extra_css", "")

    css_chunks = [
        f"@page {{ size: {page_size} {orientation}; margin: {margin}; }}",
        "body {"
        f" padding: {padding};"
        f" font-family: {font_family};"
        f" font-size: {font_size};"
        f" color: {text_color};"
        f" background: {background_color};"
        " }",
        f".pdf-content {{ margin-bottom: {content_spacing}; }}",
    ]

    if extra_css:
        css_chunks.append(str(extra_css))
    if extra_css_chunks:
        for chunk in extra_css_chunks:
            if chunk:
                css_chunks.append(str(chunk))

    return "\n".join(css_chunks)


def _expand_box_shorthand(value: Any) -> tuple[str, str, str, str]:
    raw = str(value or "0").split()
    if len(raw) == 1:
        return raw[0], raw[0], raw[0], raw[0]
    if len(raw) == 2:
        return raw[0], raw[1], raw[0], raw[1]
    if len(raw) == 3:
        return raw[0], raw[1], raw[2], raw[1]
    return raw[0], raw[1], raw[2], raw[3]


def _build_pinned_layout_css(
    *,
    has_header: bool,
    has_footer: bool,
    repeat_header: bool,
    repeat_footer: bool,
    config: dict[str, Any],
) -> str:
    """
    Build CSS for repeated or first-page-only header/footer layout.
    """
    margin_top, margin_right, margin_bottom, margin_left = _expand_box_shorthand(
        config.get("margin", "20mm")
    )
    header_spacing = config.get("header_spacing", "0mm")
    footer_spacing = config.get("footer_spacing", "0mm")
    header_height = config.get("header_height", "0mm")
    footer_height = config.get("footer_height", "0mm")
    content_spacing = config.get("content_spacing", "8mm")
    reserved_header_space = f"calc({header_height} + {header_spacing})"
    reserved_footer_space = f"calc({footer_height} + {footer_spacing})"

    css_chunks = [
        "@page {"
        f" margin-top: calc({margin_top} + {reserved_header_space if has_header and repeat_header else '0mm'});"
        f" margin-right: {margin_right};"
        f" margin-bottom: calc({margin_bottom} + {reserved_footer_space if has_footer and repeat_footer else '0mm'});"
        f" margin-left: {margin_left};"
        " }",
        "html, body { margin: 0; }",
        "* { box-sizing: border-box; }",
        ".pdf-content {"
        " position: relative;"
        f" margin-bottom: {content_spacing};"
        " }",
    ]

    if has_header:
        header_rules = [".pdf-header {"]
        if repeat_header:
            header_rules.extend(
                [
                    " position: fixed;",
                    f" top: calc(-1 * {reserved_header_space});",
                    " left: 0;",
                    " right: 0;",
                    " width: 100%;",
                ]
            )
        else:
            header_rules.extend(
                [
                    " position: running(pdf-header);",
                    " height: 0;",
                    " min-height: 0;",
                    " margin: 0;",
                    " padding: 0;",
                    " overflow: visible;",
                ]
            )
        header_rules.append(" }")
        css_chunks.extend(
            [
                "".join(header_rules),
                "@page :first {"
                f" margin-top: calc({margin_top} + {reserved_header_space});"
                " @top-center { content: element(pdf-header); vertical-align: top; margin: 0; padding: 0; }"
                " }",
            ]
        )

    if has_footer:
        footer_rules = [".pdf-footer {"]
        if repeat_footer:
            footer_rules.extend(
                [
                    " position: fixed;",
                    f" bottom: calc(-1 * {reserved_footer_space});",
                    " left: 0;",
                    " right: 0;",
                    " width: 100%;",
                ]
            )
        else:
            footer_rules.extend(
                [
                    " position: running(pdf-footer);",
                    " height: 0;",
                    " min-height: 0;",
                    " margin: 0;",
                    " padding: 0;",
                    " overflow: visible;",
                ]
            )
        footer_rules.append(" }")
        css_chunks.extend(
            [
                "".join(footer_rules),
                "@page :first {"
                f" margin-bottom: calc({margin_bottom} + {reserved_footer_space});"
                " @bottom-center { content: element(pdf-footer); vertical-align: bottom; margin: 0; padding: 0; }"
                " }",
            ]
        )

    return "\n".join(css_chunks)


def _css_escape(value: str) -> str:
    """
    Escape a string for safe inclusion in CSS content property.

    Escapes backslashes, quotes, newlines, and other control characters
    that could break out of CSS string context.
    """
    result = []
    for char in value:
        if char == "\\":
            result.append("\\\\")
        elif char == '"':
            result.append('\\"')
        elif char == "'":
            result.append("\\'")
        elif char == "\n":
            result.append("\\A ")
        elif char == "\r":
            result.append("\\D ")
        elif char == "\t":
            result.append("\\9 ")
        elif char == "{":
            result.append("\\7B ")
        elif char == "}":
            result.append("\\7D ")
        elif char == "<":
            result.append("\\3C ")
        elif char == ">":
            result.append("\\3E ")
        elif ord(char) < 32 or ord(char) == 127:
            # Escape other control characters
            result.append(f"\\{ord(char):X} ")
        else:
            result.append(char)
    return "".join(result)


def _page_stamp_content(text: str) -> str:
    tokens = re.split(r"(\{page\}|\{pages\})", text)
    parts: list[str] = []
    for token in tokens:
        if token == "{page}":
            parts.append("counter(page)")
        elif token == "{pages}":
            parts.append("counter(pages)")
        elif token:
            parts.append(f'"{_css_escape(token)}"')
    return " ".join(parts) if parts else '""'


def _build_page_stamp_css(page_stamps: Optional[dict[str, Any]]) -> str:
    if not page_stamps:
        return ""

    position_map = {
        "top-left": "@top-left",
        "top-center": "@top-center",
        "top-right": "@top-right",
        "bottom-left": "@bottom-left",
        "bottom-center": "@bottom-center",
        "bottom-right": "@bottom-right",
    }
    position = position_map.get(
        str(page_stamps.get("position", "bottom-right")).lower(), "@bottom-right"
    )
    text = str(page_stamps.get("text", "Page {page} of {pages}"))
    font_size = str(page_stamps.get("font_size", "9pt"))
    color = str(page_stamps.get("color", "#666666"))
    content = _page_stamp_content(text)

    return (
        "@page { "
        f"{position} {{ content: {content}; font-size: {font_size}; color: {color}; }} "
        "}"
    )


def _build_watermark_assets(watermark: Optional[dict[str, Any]]) -> tuple[str, str]:
    if not watermark:
        return "", ""

    if str(watermark.get("mode", "css")).lower() == "overlay":
        return "", ""

    html_content = watermark.get("html")
    text = watermark.get("text")
    if html_content:
        watermark_html = str(html_content)
    elif text:
        watermark_html = f"<div class='pdf-watermark'>{html.escape(str(text))}</div>"
    else:
        return "", ""

    opacity = watermark.get("opacity", 0.12)
    rotation = watermark.get("rotation", -30)
    font_size = watermark.get("font_size", "48pt")
    color = watermark.get("color", "#999999")
    z_index = watermark.get("z_index", 0)

    watermark_css = (
        ".pdf-watermark {"
        " position: fixed;"
        " top: 50%;"
        " left: 50%;"
        f" transform: translate(-50%, -50%) rotate({rotation}deg);"
        f" opacity: {opacity};"
        f" font-size: {font_size};"
        f" color: {color};"
        f" z-index: {z_index};"
        " pointer-events: none;"
        " white-space: nowrap;"
        "}"
    )

    return watermark_html, watermark_css


def render_template_html(
    *,
    header_html: str,
    content_html: str,
    footer_html: str,
    repeat_header: Optional[bool] = True,
    repeat_footer: Optional[bool] = True,
    config: dict[str, Any],
    postprocess: Optional[dict[str, Any]] = None,
) -> str:
    """
    Compose a complete HTML document from header, content, and footer HTML.

    Args:
        header_html: Rendered header HTML.
        content_html: Rendered content HTML.
        footer_html: Rendered footer HTML.
        repeat_header: When True, render the header on every page. Any other value limits it to the first page.
        repeat_footer: When True, render the footer on every page. Any other value limits it to the first page.
        config: Style configuration.
        postprocess: Optional postprocessing configuration.

    Returns:
        Complete HTML document string.
    """
    postprocess_config = _resolve_postprocess_config(config, postprocess)
    postprocess_enabled = bool(postprocess_config.get("enable", False))
    page_stamps = _normalize_page_stamps(
        (postprocess_config.get("page_stamps") if postprocess_enabled else None)
        or config.get("page_stamps")
    )
    watermark = _normalize_watermark(
        (postprocess_config.get("watermark") if postprocess_enabled else None)
        or config.get("watermark")
    )
    header_html, header_css_chunks = _normalize_html_fragment(header_html)
    content_html, content_css_chunks = _normalize_html_fragment(content_html)
    footer_html, footer_css_chunks = _normalize_html_fragment(footer_html)
    has_header = bool(header_html and header_html.strip())
    has_footer = bool(footer_html and footer_html.strip())

    page_stamp_css = _build_page_stamp_css(page_stamps)
    watermark_html, watermark_css = _build_watermark_assets(watermark)
    pinned_layout_css = _build_pinned_layout_css(
        has_header=has_header,
        has_footer=has_footer,
        repeat_header=repeat_header is True,
        repeat_footer=repeat_footer is True,
        config=config,
    )
    if watermark_css:
        watermark_css += (
            ".pdf-header,.pdf-content,.pdf-footer{position:relative;z-index:1;}"
        )

    style_block = _build_style_block(
        config,
        extra_css_chunks=[
            *header_css_chunks,
            *content_css_chunks,
            *footer_css_chunks,
            pinned_layout_css,
            page_stamp_css,
            watermark_css,
        ],
    )
    header_block = f"<div class='pdf-header'>{header_html}</div>" if has_header else ""
    footer_block = f"<div class='pdf-footer'>{footer_html}</div>" if has_footer else ""
    return (
        "<html><head><meta charset='utf-8'><style>"
        f"{style_block}"
        "</style></head><body>"
        f"{watermark_html}"
        f"{header_block}"
        f"<div class='pdf-content'>{content_html}</div>"
        f"{footer_block}"
        "</body></html>"
    )
