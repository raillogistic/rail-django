"""
Markdown documentation generation.
"""

import logging
import re
from typing import Optional

from ..schema_introspector import FieldInfo, SchemaIntrospection, TypeInfo
from .config import DocumentationConfig

logger = logging.getLogger(__name__)


class MarkdownGeneratorMixin:
    """Mixin for generating Markdown documentation."""

    def _generate_markdown_header(self, introspection: SchemaIntrospection) -> str:
        """Generate Markdown header section."""
        header = [f"# {introspection.schema_name} GraphQL Schema Documentation", ""]
        if introspection.description:
            header.extend([introspection.description, ""])
        metadata = ["## Schema Information", "", "| Property | Value |", "|----------|-------|"]
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
        toc = ["## Table of Contents", "", "- [Schema Information](#schema-information)", "- [Overview](#overview)", "- [Root Types](#root-types)"]
        if introspection.queries: toc.append("  - [Query](#query)")
        if introspection.mutations: toc.append("  - [Mutation](#mutation)")
        if introspection.subscriptions: toc.append("  - [Subscription](#subscription)")
        toc.append("- [Types](#types)")
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
        overview = ["## Overview", "", f"This GraphQL schema contains **{introspection.complexity.total_types}** types with **{introspection.complexity.total_fields}** fields.", ""]
        type_breakdown = []
        if introspection.complexity.object_types > 0: type_breakdown.append(f"{introspection.complexity.object_types} Object types")
        if introspection.complexity.interface_types > 0: type_breakdown.append(f"{introspection.complexity.interface_types} Interface types")
        if introspection.complexity.union_types > 0: type_breakdown.append(f"{introspection.complexity.union_types} Union types")
        if introspection.complexity.enum_types > 0: type_breakdown.append(f"{introspection.complexity.enum_types} Enum types")
        if introspection.complexity.input_types > 0: type_breakdown.append(f"{introspection.complexity.input_types} Input types")
        if introspection.complexity.scalar_types > 0: type_breakdown.append(f"{introspection.complexity.scalar_types} Scalar types")
        if type_breakdown:
            overview.extend(["### Type Distribution", "", "- " + "\n- ".join(type_breakdown), ""])
        operations = []
        if introspection.queries: operations.append(f"**{len(introspection.queries)}** Query operations")
        if introspection.mutations: operations.append(f"**{len(introspection.mutations)}** Mutation operations")
        if introspection.subscriptions: operations.append(f"**{len(introspection.subscriptions)}** Subscription operations")
        if operations:
            overview.extend(["### Available Operations", "", "- " + "\n- ".join(operations), ""])
        return '\n'.join(overview)

    def _generate_markdown_root_types(self, introspection: SchemaIntrospection) -> str:
        """Generate root types section."""
        content = ["## Root Types", ""]
        if introspection.queries:
            content.extend(["### Query", "", "Available query operations:", ""])
            for field in introspection.queries: content.append(self._format_field_markdown(field, "query"))
            content.append("")
        if introspection.mutations:
            content.extend(["### Mutation", "", "Available mutation operations:", ""])
            for field in introspection.mutations: content.append(self._format_field_markdown(field, "mutation"))
            content.append("")
        if introspection.subscriptions:
            content.extend(["### Subscription", "", "Available subscription operations:", ""])
            for field in introspection.subscriptions: content.append(self._format_field_markdown(field, "subscription"))
            content.append("")
        return '\n'.join(content)

    def _generate_markdown_types(self, introspection: SchemaIntrospection) -> str:
        """Generate types section."""
        content = ["## Types", ""]
        type_categories = self._group_types_by_category(introspection.types)
        for category in sorted(type_categories.keys()):
            content.extend([f"### {category}", ""])
            for type_name in sorted(type_categories[category].keys()):
                content.append(self._format_type_markdown(type_categories[category][type_name]))
                content.append("")
        return '\n'.join(content)

    def _generate_markdown_directives(self, introspection: SchemaIntrospection) -> str:
        """Generate directives section."""
        content = ["## Directives", ""]
        for directive_name in sorted(introspection.directives.keys()):
            directive = introspection.directives[directive_name]
            content.extend([f"### @{directive_name}", ""])
            if directive.description: content.extend([directive.description, ""])
            if directive.locations: content.extend(["**Locations:** " + ", ".join(f'`{loc}`' for loc in directive.locations), ""])
            if directive.args:
                content.extend(["**Arguments:**", ""])
                for arg in directive.args:
                    arg_line = f"- `{arg['name']}: {arg['type']}`"
                    if arg.get('description'): arg_line += f" - {arg['description']}"
                    content.append(arg_line)
                content.append("")
        return '\n'.join(content)

    def _generate_markdown_complexity(self, introspection: SchemaIntrospection) -> str:
        """Generate complexity metrics section."""
        complexity = introspection.complexity
        content = ["## Complexity Metrics", "", "| Metric | Value |", "|--------|-------|", f"| Total Types | {complexity.total_types} |", f"| Total Fields | {complexity.total_fields} |", f"| Total Arguments | {complexity.total_arguments} |", f"| Max Depth | {complexity.max_depth} |", f"| Deprecated Fields | {complexity.deprecated_fields} |", ""]
        if complexity.circular_references:
            content.extend(["### Circular References", "", "The following circular references were detected:", ""])
            for ref in complexity.circular_references: content.append(f"- `{ref}`")
            content.append("")
        return '\n'.join(content)

    def _format_field_markdown(self, field: FieldInfo, context: str = "") -> str:
        """Format a field for Markdown output."""
        field_line = f"#### `{field.name}: {field.type}`"
        if field.is_deprecated: field_line += " âš ï¸ *Deprecated*"
        lines = [field_line, ""]
        if field.description: lines.extend([field.description, ""])
        if field.args:
            lines.extend(["**Arguments:**", ""])
            for arg in field.args:
                arg_line = f"- `{arg['name']}: {arg['type']}`"
                if arg.get('description'): arg_line += f" - {arg['description']}"
                if arg.get('default_value') is not None: arg_line += f" (default: `{arg['default_value']}`)"
                lines.append(arg_line)
            lines.append("")
        if field.is_deprecated and field.deprecation_reason: lines.extend([f"**Deprecation reason:** {field.deprecation_reason}", ""])
        if self.config.include_examples and context:
            example = self._generate_field_example(field, context)
            if example: lines.extend(["**Example:**", "", "```graphql", example, "```", ""])
        return '\n'.join(lines)

    def _format_type_markdown(self, type_info: TypeInfo) -> str:
        """Format a type for Markdown output."""
        type_line = f"#### `{type_info.name}` ({type_info.kind})"
        if type_info.is_deprecated: type_line += " âš ï¸ *Deprecated*"
        lines = [type_line, ""]
        if type_info.description: lines.extend([type_info.description, ""])
        if type_info.interfaces: lines.extend([f"**Implements:** {', '.join(f'`{iface}`' for iface in type_info.interfaces)}", ""])
        if type_info.possible_types: lines.extend([f"**Possible types:** {', '.join(f'`{ptype}`' for ptype in type_info.possible_types)}", ""])
        if type_info.fields:
            lines.extend(["**Fields:**", ""])
            for field_dict in type_info.fields:
                field_line = f"- `{field_dict['name']}: {field_dict['type']}`"
                if field_dict.get('description'): field_line += f" - {field_dict['description']}"
                if field_dict.get('is_deprecated'): field_line += " âš ï¸ *Deprecated*"
                lines.append(field_line)
            lines.append("")
        if type_info.input_fields:
            lines.extend(["**Input fields:**", ""])
            for field_dict in type_info.input_fields:
                field_line = f"- `{field_dict['name']}: {field_dict['type']}`"
                if field_dict.get('description'): field_line += f" - {field_dict['description']}"
                if field_dict.get('default_value') is not None: field_line += f" (default: `{field_dict['default_value']}`)"
                lines.append(field_line)
            lines.append("")
        if type_info.enum_values:
            lines.extend(["**Values:**", ""])
            for enum_dict in type_info.enum_values:
                enum_line = f"- `{enum_dict['name']}`"
                if enum_dict.get('description'): enum_line += f" - {enum_dict['description']}"
                if enum_dict.get('is_deprecated'): enum_line += " âš ï¸ *Deprecated*"
                lines.append(enum_line)
            lines.append("")
        return '\n'.join(lines)

    def _generate_field_example(self, field: FieldInfo, context: str) -> Optional[str]:
        """Generate a simple example for a field."""
        if not self.config.include_examples: return None
        if context in ("query", "mutation"):
            if field.args:
                args = ", ".join(f"{arg['name']}: {self._get_example_value(arg['type'])}" for arg in field.args[:2])
                return f"""{context} {{
  {field.name}({args}) {{
    # fields
  }}
}}"""
            else:
                return f"""{context} {{
  {field.name} {{
    # fields
  }}
}}"""
        return None

    def _get_example_value(self, type_str: str) -> str:
        """Get an example value for a GraphQL type."""
        base_type = re.sub(r'[![]]', '', type_str)
        scalar_examples = {'String': '"example"', 'Int': '42', 'Float': '3.14', 'Boolean': 'true', 'ID': '"123"'}
        return scalar_examples.get(base_type, f'"{base_type.lower()}_value"')

    def _group_types_by_category(self, types: dict[str, TypeInfo]) -> dict[str, dict[str, TypeInfo]]:
        """Group types by category."""
        categories = {'Object Types': {}, 'Interface Types': {}, 'Union Types': {}, 'Enum Types': {}, 'Input Types': {}, 'Scalar Types': {}}
        for type_name, type_info in types.items():
            if not self.config.include_internal_types and type_name.startswith('__'): continue
            if not self.config.include_scalars and type_info.kind == 'SCALAR':
                if type_name not in ['String', 'Int', 'Float', 'Boolean', 'ID']:
                    categories['Scalar Types'][type_name] = type_info
                continue
            if type_info.kind == 'OBJECT': categories['Object Types'][type_name] = type_info
            elif type_info.kind == 'INTERFACE': categories['Interface Types'][type_name] = type_info
            elif type_info.kind == 'UNION': categories['Union Types'][type_name] = type_info
            elif type_info.kind == 'ENUM': categories['Enum Types'][type_name] = type_info
            elif type_info.kind == 'INPUT_OBJECT': categories['Input Types'][type_name] = type_info
            elif type_info.kind == 'SCALAR': categories['Scalar Types'][type_name] = type_info
        return {cat: td for cat, td in categories.items() if td}
