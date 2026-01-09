"""
Documentation generation module.

This module provides capabilities for generating comprehensive documentation
from GraphQL schema introspections, including HTML, Markdown, and JSON formats.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .schema_comparator import SchemaComparison
from .schema_introspector import FieldInfo, SchemaIntrospection, TypeInfo

logger = logging.getLogger(__name__)


@dataclass
class DocumentationConfig:
    """Configuration for documentation generation."""
    include_deprecated: bool = True
    include_internal_types: bool = False
    include_scalars: bool = True
    include_directives: bool = True
    include_examples: bool = True
    include_complexity_metrics: bool = True
    group_by_category: bool = True
    generate_toc: bool = True
    custom_css: Optional[str] = None
    custom_templates: Optional[Dict[str, str]] = None


class DocumentationGenerator:
    """
    Comprehensive GraphQL schema documentation generator.

    Generates documentation in multiple formats (HTML, Markdown, JSON)
    from schema introspections and comparisons.
    """

    def __init__(self, config: DocumentationConfig = None):
        self.config = config or DocumentationConfig()
        self.logger = logging.getLogger(__name__)

    def generate_markdown_documentation(self, introspection: SchemaIntrospection,
                                        output_path: Optional[str] = None) -> str:
        """
        Generate comprehensive Markdown documentation.

        Args:
            introspection: Schema introspection data
            output_path: Optional path to save the documentation

        Returns:
            Generated Markdown content
        """
        self.logger.info(
            f"Generating Markdown documentation for schema '{introspection.schema_name}'")

        content = []

        # Header
        content.append(self._generate_markdown_header(introspection))

        # Table of Contents
        if self.config.generate_toc:
            content.append(self._generate_markdown_toc(introspection))

        # Overview
        content.append(self._generate_markdown_overview(introspection))

        # Root Types
        content.append(self._generate_markdown_root_types(introspection))

        # Types
        content.append(self._generate_markdown_types(introspection))

        # Directives
        if self.config.include_directives and introspection.directives:
            content.append(self._generate_markdown_directives(introspection))

        # Complexity Metrics
        if self.config.include_complexity_metrics:
            content.append(self._generate_markdown_complexity(introspection))

        markdown_content = '\n\n'.join(content)

        if output_path:
            Path(output_path).write_text(markdown_content, encoding='utf-8')
            self.logger.info(f"Markdown documentation saved to {output_path}")

        return markdown_content

    def generate_html_documentation(self, introspection: SchemaIntrospection,
                                    output_path: Optional[str] = None) -> str:
        """
        Generate comprehensive HTML documentation.

        Args:
            introspection: Schema introspection data
            output_path: Optional path to save the documentation

        Returns:
            Generated HTML content
        """
        self.logger.info(f"Generating HTML documentation for schema '{introspection.schema_name}'")

        # Generate Markdown first
        markdown_content = self.generate_markdown_documentation(introspection)

        # Convert to HTML (simplified conversion)
        html_content = self._markdown_to_html(markdown_content, introspection)

        if output_path:
            Path(output_path).write_text(html_content, encoding='utf-8')
            self.logger.info(f"HTML documentation saved to {output_path}")

        return html_content

    def generate_json_documentation(self, introspection: SchemaIntrospection,
                                    output_path: Optional[str] = None) -> str:
        """
        Generate JSON documentation.

        Args:
            introspection: Schema introspection data
            output_path: Optional path to save the documentation

        Returns:
            Generated JSON content
        """
        self.logger.info(f"Generating JSON documentation for schema '{introspection.schema_name}'")

        json_data = introspection.to_dict()
        json_content = json.dumps(json_data, indent=2, ensure_ascii=False)

        if output_path:
            Path(output_path).write_text(json_content, encoding='utf-8')
            self.logger.info(f"JSON documentation saved to {output_path}")

        return json_content

    def generate_comparison_report(self, comparison: SchemaComparison,
                                   output_path: Optional[str] = None,
                                   format: str = 'markdown') -> str:
        """
        Generate schema comparison report.

        Args:
            comparison: Schema comparison data
            output_path: Optional path to save the report
            format: Output format ('markdown', 'html', 'json')

        Returns:
            Generated report content
        """
        self.logger.info(f"Generating {format} comparison report")

        if format == 'markdown':
            content = self._generate_markdown_comparison(comparison)
        elif format == 'html':
            markdown_content = self._generate_markdown_comparison(comparison)
            content = self._markdown_to_html(markdown_content, None)
        elif format == 'json':
            content = json.dumps(comparison.to_dict(), indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported format: {format}")

        if output_path:
            Path(output_path).write_text(content, encoding='utf-8')
            self.logger.info(f"Comparison report saved to {output_path}")

        return content

    def _generate_markdown_header(self, introspection: SchemaIntrospection) -> str:
        """Generate Markdown header section."""
        header = [
            f"# {introspection.schema_name} GraphQL Schema Documentation",
            ""
        ]

        if introspection.description:
            header.extend([
                introspection.description,
                ""
            ])

        # Metadata table
        metadata = [
            "## Schema Information",
            "",
            "| Property | Value |",
            "|----------|-------|"
        ]

        if introspection.version:
            metadata.append(f"| Version | `{introspection.version}` |")

        metadata.extend([
            f"| Generated | {introspection.introspection_date.strftime('%Y-%m-%d %H:%M:%S')} |",
            f"| Total Types | {introspection.complexity.total_types} |",
            f"| Total Fields | {introspection.complexity.total_fields} |"
        ])

        if introspection.tags:
            metadata.append(f"| Tags | {', '.join(f'`{tag}`' for tag in introspection.tags)} |")

        header.extend(metadata)

        return '\n'.join(header)

    def _generate_markdown_toc(self, introspection: SchemaIntrospection) -> str:
        """Generate Table of Contents."""
        toc = [
            "## Table of Contents",
            "",
            "- [Schema Information](#schema-information)",
            "- [Overview](#overview)",
            "- [Root Types](#root-types)"
        ]

        if introspection.queries:
            toc.append("  - [Query](#query)")
        if introspection.mutations:
            toc.append("  - [Mutation](#mutation)")
        if introspection.subscriptions:
            toc.append("  - [Subscription](#subscription)")

        toc.append("- [Types](#types)")

        # Group types by category
        type_categories = self._group_types_by_category(introspection.types)
        for category in sorted(type_categories.keys()):
            toc.append(f"  - [{category}](#{category.lower().replace(' ', '-')})")

        if self.config.include_directives and introspection.directives:
            toc.append("- [Directives](#directives)")

        if self.config.include_complexity_metrics:
            toc.append("- [Complexity Metrics](#complexity-metrics)")

        return '\n'.join(toc)

    def _generate_markdown_overview(self, introspection: SchemaIntrospection) -> str:
        """Generate overview section."""
        overview = [
            "## Overview",
            ""
        ]

        # Schema statistics
        stats = [
            f"This GraphQL schema contains **{introspection.complexity.total_types}** types with **{introspection.complexity.total_fields}** fields.",
            ""
        ]

        # Type breakdown
        type_breakdown = []
        if introspection.complexity.object_types > 0:
            type_breakdown.append(f"{introspection.complexity.object_types} Object types")
        if introspection.complexity.interface_types > 0:
            type_breakdown.append(f"{introspection.complexity.interface_types} Interface types")
        if introspection.complexity.union_types > 0:
            type_breakdown.append(f"{introspection.complexity.union_types} Union types")
        if introspection.complexity.enum_types > 0:
            type_breakdown.append(f"{introspection.complexity.enum_types} Enum types")
        if introspection.complexity.input_types > 0:
            type_breakdown.append(f"{introspection.complexity.input_types} Input types")
        if introspection.complexity.scalar_types > 0:
            type_breakdown.append(f"{introspection.complexity.scalar_types} Scalar types")

        if type_breakdown:
            stats.extend([
                "### Type Distribution",
                "",
                "- " + "\n- ".join(type_breakdown),
                ""
            ])

        # Root operations
        operations = []
        if introspection.queries:
            operations.append(f"**{len(introspection.queries)}** Query operations")
        if introspection.mutations:
            operations.append(f"**{len(introspection.mutations)}** Mutation operations")
        if introspection.subscriptions:
            operations.append(f"**{len(introspection.subscriptions)}** Subscription operations")

        if operations:
            stats.extend([
                "### Available Operations",
                "",
                "- " + "\n- ".join(operations),
                ""
            ])

        overview.extend(stats)

        return '\n'.join(overview)

    def _generate_markdown_root_types(self, introspection: SchemaIntrospection) -> str:
        """Generate root types section."""
        content = [
            "## Root Types",
            ""
        ]

        # Query
        if introspection.queries:
            content.extend([
                "### Query",
                "",
                "Available query operations:",
                ""
            ])

            for field in introspection.queries:
                content.append(self._format_field_markdown(field, "query"))

            content.append("")

        # Mutation
        if introspection.mutations:
            content.extend([
                "### Mutation",
                "",
                "Available mutation operations:",
                ""
            ])

            for field in introspection.mutations:
                content.append(self._format_field_markdown(field, "mutation"))

            content.append("")

        # Subscription
        if introspection.subscriptions:
            content.extend([
                "### Subscription",
                "",
                "Available subscription operations:",
                ""
            ])

            for field in introspection.subscriptions:
                content.append(self._format_field_markdown(field, "subscription"))

            content.append("")

        return '\n'.join(content)

    def _generate_markdown_types(self, introspection: SchemaIntrospection) -> str:
        """Generate types section."""
        content = [
            "## Types",
            ""
        ]

        # Group types by category
        type_categories = self._group_types_by_category(introspection.types)

        for category in sorted(type_categories.keys()):
            content.extend([
                f"### {category}",
                ""
            ])

            types_in_category = type_categories[category]
            for type_name in sorted(types_in_category.keys()):
                type_info = types_in_category[type_name]
                content.append(self._format_type_markdown(type_info))
                content.append("")

        return '\n'.join(content)

    def _generate_markdown_directives(self, introspection: SchemaIntrospection) -> str:
        """Generate directives section."""
        content = [
            "## Directives",
            ""
        ]

        for directive_name in sorted(introspection.directives.keys()):
            directive = introspection.directives[directive_name]
            content.extend([
                f"### @{directive_name}",
                ""
            ])

            if directive.description:
                content.extend([
                    directive.description,
                    ""
                ])

            # Locations
            if directive.locations:
                content.extend([
                    "**Locations:** " + ", ".join(f"`{loc}`" for loc in directive.locations),
                    ""
                ])

            # Arguments
            if directive.args:
                content.extend([
                    "**Arguments:**",
                    ""
                ])

                for arg in directive.args:
                    arg_line = f"- `{arg['name']}: {arg['type']}`"
                    if arg.get('description'):
                        arg_line += f" - {arg['description']}"
                    content.append(arg_line)

                content.append("")

        return '\n'.join(content)

    def _generate_markdown_complexity(self, introspection: SchemaIntrospection) -> str:
        """Generate complexity metrics section."""
        complexity = introspection.complexity

        content = [
            "## Complexity Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Types | {complexity.total_types} |",
            f"| Total Fields | {complexity.total_fields} |",
            f"| Total Arguments | {complexity.total_arguments} |",
            f"| Max Depth | {complexity.max_depth} |",
            f"| Deprecated Fields | {complexity.deprecated_fields} |",
            ""
        ]

        if complexity.circular_references:
            content.extend([
                "### Circular References",
                "",
                "The following circular references were detected:",
                ""
            ])

            for ref in complexity.circular_references:
                content.append(f"- `{ref}`")

            content.append("")

        return '\n'.join(content)

    def _format_field_markdown(self, field: FieldInfo, context: str = "") -> str:
        """Format a field for Markdown output."""
        field_line = f"#### `{field.name}: {field.type}`"

        if field.is_deprecated:
            field_line += " ⚠️ *Deprecated*"

        lines = [field_line, ""]

        if field.description:
            lines.extend([field.description, ""])

        if field.args:
            lines.extend(["**Arguments:**", ""])
            for arg in field.args:
                arg_line = f"- `{arg['name']}: {arg['type']}`"
                if arg.get('description'):
                    arg_line += f" - {arg['description']}"
                if arg.get('default_value') is not None:
                    arg_line += f" (default: `{arg['default_value']}`)"
                lines.append(arg_line)
            lines.append("")

        if field.is_deprecated and field.deprecation_reason:
            lines.extend([
                f"**Deprecation reason:** {field.deprecation_reason}",
                ""
            ])

        if self.config.include_examples and context:
            example = self._generate_field_example(field, context)
            if example:
                lines.extend([
                    "**Example:**",
                    "",
                    "```graphql",
                    example,
                    "```",
                    ""
                ])

        return '\n'.join(lines)

    def _format_type_markdown(self, type_info: TypeInfo) -> str:
        """Format a type for Markdown output."""
        type_line = f"#### `{type_info.name}` ({type_info.kind})"

        if type_info.is_deprecated:
            type_line += " ⚠️ *Deprecated*"

        lines = [type_line, ""]

        if type_info.description:
            lines.extend([type_info.description, ""])

        # Interfaces (for object types)
        if type_info.interfaces:
            lines.extend([
                f"**Implements:** {', '.join(f'`{iface}`' for iface in type_info.interfaces)}",
                ""
            ])

        # Possible types (for unions/interfaces)
        if type_info.possible_types:
            lines.extend([
                f"**Possible types:** {', '.join(f'`{ptype}`' for ptype in type_info.possible_types)}",
                ""
            ])

        # Fields
        if type_info.fields:
            lines.extend(["**Fields:**", ""])
            for field_dict in type_info.fields:
                field_line = f"- `{field_dict['name']}: {field_dict['type']}`"
                if field_dict.get('description'):
                    field_line += f" - {field_dict['description']}"
                if field_dict.get('is_deprecated'):
                    field_line += " ⚠️ *Deprecated*"
                lines.append(field_line)
            lines.append("")

        # Input fields
        if type_info.input_fields:
            lines.extend(["**Input fields:**", ""])
            for field_dict in type_info.input_fields:
                field_line = f"- `{field_dict['name']}: {field_dict['type']}`"
                if field_dict.get('description'):
                    field_line += f" - {field_dict['description']}"
                if field_dict.get('default_value') is not None:
                    field_line += f" (default: `{field_dict['default_value']}`)"
                lines.append(field_line)
            lines.append("")

        # Enum values
        if type_info.enum_values:
            lines.extend(["**Values:**", ""])
            for enum_dict in type_info.enum_values:
                enum_line = f"- `{enum_dict['name']}`"
                if enum_dict.get('description'):
                    enum_line += f" - {enum_dict['description']}"
                if enum_dict.get('is_deprecated'):
                    enum_line += " ⚠️ *Deprecated*"
                lines.append(enum_line)
            lines.append("")

        return '\n'.join(lines)

    def _generate_field_example(self, field: FieldInfo, context: str) -> Optional[str]:
        """Generate a simple example for a field."""
        if not self.config.include_examples:
            return None

        # Simple example generation
        if context == "query":
            if field.args:
                args = ", ".join(f"{arg['name']}: {self._get_example_value(arg['type'])}"
                                 for arg in field.args[:2])  # Limit to first 2 args
                return f"{context} {{\n  {field.name}({args}) {{\n    # fields\n  }}\n}}"
            else:
                return f"{context} {{\n  {field.name} {{\n    # fields\n  }}\n}}"

        elif context == "mutation":
            if field.args:
                args = ", ".join(f"{arg['name']}: {self._get_example_value(arg['type'])}"
                                 for arg in field.args[:2])
                return f"{context} {{\n  {field.name}({args}) {{\n    # return fields\n  }}\n}}"
            else:
                return f"{context} {{\n  {field.name} {{\n    # return fields\n  }}\n}}"

        return None

    def _get_example_value(self, type_str: str) -> str:
        """Get an example value for a GraphQL type."""
        # Remove non-null and list wrappers
        base_type = re.sub(r'[!\[\]]', '', type_str)

        # Common scalar examples
        scalar_examples = {
            'String': '"example"',
            'Int': '42',
            'Float': '3.14',
            'Boolean': 'true',
            'ID': '"123"'
        }

        return scalar_examples.get(base_type, f'"{base_type.lower()}_value"')

    def _group_types_by_category(self, types: Dict[str, TypeInfo]) -> Dict[str, Dict[str, TypeInfo]]:
        """Group types by category for better organization."""
        categories = {
            'Object Types': {},
            'Interface Types': {},
            'Union Types': {},
            'Enum Types': {},
            'Input Types': {},
            'Scalar Types': {}
        }

        for type_name, type_info in types.items():
            # Skip internal types unless configured to include them
            if not self.config.include_internal_types and type_name.startswith('__'):
                continue

            # Skip scalars unless configured to include them
            if not self.config.include_scalars and type_info.kind == 'SCALAR':
                # Always include custom scalars
                if type_name not in ['String', 'Int', 'Float', 'Boolean', 'ID']:
                    categories['Scalar Types'][type_name] = type_info
                continue

            if type_info.kind == 'OBJECT':
                categories['Object Types'][type_name] = type_info
            elif type_info.kind == 'INTERFACE':
                categories['Interface Types'][type_name] = type_info
            elif type_info.kind == 'UNION':
                categories['Union Types'][type_name] = type_info
            elif type_info.kind == 'ENUM':
                categories['Enum Types'][type_name] = type_info
            elif type_info.kind == 'INPUT_OBJECT':
                categories['Input Types'][type_name] = type_info
            elif type_info.kind == 'SCALAR':
                categories['Scalar Types'][type_name] = type_info

        # Remove empty categories
        return {category: types_dict for category, types_dict in categories.items()
                if types_dict}

    def _markdown_to_html(self, markdown_content: str, introspection: Optional[SchemaIntrospection]) -> str:
        """Convert Markdown to HTML (simplified implementation)."""
        # This is a very basic Markdown to HTML converter
        # In a real implementation, you'd use a proper Markdown library

        html_lines = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"    <title>{introspection.schema_name if introspection else 'GraphQL Schema'} Documentation</title>",
            "    <style>",
            self._get_default_css(),
            "    </style>",
            "</head>",
            "<body>",
            "    <div class='container'>"
        ]

        # Simple Markdown to HTML conversion
        lines = markdown_content.split('\n')
        in_code_block = False

        for line in lines:
            if line.startswith('```'):
                if in_code_block:
                    html_lines.append("        </code></pre>")
                    in_code_block = False
                else:
                    lang = line[3:].strip() or 'text'
                    html_lines.append(f"        <pre><code class='language-{lang}'>")
                    in_code_block = True
            elif in_code_block:
                html_lines.append(f"        {line}")
            elif line.startswith('# '):
                html_lines.append(f"        <h1>{line[2:]}</h1>")
            elif line.startswith('## '):
                html_lines.append(f"        <h2>{line[3:]}</h2>")
            elif line.startswith('### '):
                html_lines.append(f"        <h3>{line[4:]}</h3>")
            elif line.startswith('#### '):
                html_lines.append(f"        <h4>{line[5:]}</h4>")
            elif line.startswith('- '):
                html_lines.append(f"        <li>{line[2:]}</li>")
            elif line.startswith('| '):
                # Simple table handling
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                html_lines.append(
                    f"        <tr>{''.join(f'<td>{cell}</td>' for cell in cells)}</tr>")
            elif line.strip():
                html_lines.append(f"        <p>{line}</p>")
            else:
                html_lines.append("")

        html_lines.extend([
            "    </div>",
            "</body>",
            "</html>"
        ])

        return '\n'.join(html_lines)

    def _get_default_css(self) -> str:
        """Get default CSS for HTML documentation."""
        if self.config.custom_css:
            return self.config.custom_css

        return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1, h2, h3, h4 {
            color: #2c3e50;
            margin-top: 2em;
            margin-bottom: 1em;
        }
        h1 {
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }
        code {
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Consolas', monospace;
        }
        pre {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            border-left: 4px solid #3498db;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f8f9fa;
            font-weight: 600;
        }
        ul, ol {
            padding-left: 30px;
        }
        li {
            margin: 5px 0;
        }
        .deprecated {
            color: #e74c3c;
            text-decoration: line-through;
        }
        """

    def _generate_markdown_comparison(self, comparison: SchemaComparison) -> str:
        """Generate Markdown comparison report."""
        content = [
            f"# Schema Comparison Report",
            "",
            f"**From:** {comparison.old_schema_name} ({comparison.old_version or 'unknown version'})",
            f"**To:** {comparison.new_schema_name} ({comparison.new_version or 'unknown version'})",
            f"**Generated:** {comparison.comparison_date.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
            f"- **Total Changes:** {comparison.total_changes}",
            f"- **Breaking Changes:** {comparison.breaking_changes}",
            f"- **Non-Breaking Changes:** {comparison.non_breaking_changes}",
            f"- **Breaking Change Level:** {comparison.breaking_change_level.value}",
            f"- **Migration Required:** {'Yes' if comparison.migration_required else 'No'}",
            f"- **Compatibility Score:** {comparison.compatibility_score:.2%}",
            ""
        ]

        if comparison.breaking_changes > 0:
            content.extend([
                "## ⚠️ Breaking Changes",
                "",
                "The following changes may break existing clients:",
                ""
            ])

            breaking_changes = comparison.get_breaking_changes()
            for change in breaking_changes:
                content.extend([
                    f"### {change.element_path}",
                    "",
                    f"**Type:** {change.change_type.value} {change.element_type}",
                    f"**Level:** {change.breaking_level.value}",
                    f"**Description:** {change.description}",
                    ""
                ])

                if change.migration_notes:
                    content.extend([
                        f"**Migration Notes:** {change.migration_notes}",
                        ""
                    ])

        # All changes by category
        if comparison.type_changes:
            content.extend([
                "## Type Changes",
                ""
            ])
            for change in comparison.type_changes:
                content.append(
                    f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")

        if comparison.field_changes:
            content.extend([
                "## Field Changes",
                ""
            ])
            for change in comparison.field_changes:
                content.append(
                    f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")

        if comparison.argument_changes:
            content.extend([
                "## Argument Changes",
                ""
            ])
            for change in comparison.argument_changes:
                content.append(
                    f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")

        if comparison.directive_changes:
            content.extend([
                "## Directive Changes",
                ""
            ])
            for change in comparison.directive_changes:
                content.append(
                    f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")

        return '\n'.join(content)
