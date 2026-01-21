"""
Comparison report generation.
"""

from ..comparison import SchemaComparison

class ComparisonGeneratorMixin:
    """Mixin for generating comparison reports."""

    def _generate_markdown_comparison(self, comparison: SchemaComparison) -> str:
        """Generate Markdown comparison report."""
        content = [
            f"# Schema Comparison Report", "",
            f"**From:** {comparison.old_schema_name} ({comparison.old_version or 'unknown version'})",
            f"**To:** {comparison.new_schema_name} ({comparison.new_version or 'unknown version'})",
            f"**Generated:** {comparison.comparison_date.strftime('%Y-%m-%d %H:%M:%S')}", "",
            "## Summary", "",
            f"- **Total Changes:** {comparison.total_changes}",
            f"- **Breaking Changes:** {comparison.breaking_changes}",
            f"- **Non-Breaking Changes:** {comparison.non_breaking_changes}",
            f"- **Breaking Change Level:** {comparison.breaking_change_level.value}",
            f"- **Migration Required:** {'Yes' if comparison.migration_required else 'No'}",
            f"- **Compatibility Score:** {comparison.compatibility_score:.2%}", ""
        ]
        if comparison.breaking_changes > 0:
            content.extend(["## âš ï¸ Breaking Changes", "", "The following changes may break existing clients:", ""])
            for change in comparison.get_breaking_changes():
                content.extend([f"### {change.element_path}", "", f"**Type:** {change.change_type.value} {change.element_type}", f"**Level:** {change.breaking_level.value}", f"**Description:** {change.description}", ""])
                if change.migration_notes: content.extend([f"**Migration Notes:** {change.migration_notes}", ""])
        if comparison.type_changes:
            content.extend(["## Type Changes", ""])
            for change in comparison.type_changes: content.append(f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")
        if comparison.field_changes:
            content.extend(["## Field Changes", ""])
            for change in comparison.field_changes: content.append(f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")
        if comparison.argument_changes:
            content.extend(["## Argument Changes", ""])
            for change in comparison.argument_changes: content.append(f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")
        if comparison.directive_changes:
            content.extend(["## Directive Changes", ""])
            for change in comparison.directive_changes: content.append(f"- {change.change_type.value}: `{change.element_path}` - {change.description}")
            content.append("")
        return '\n'.join(content)
