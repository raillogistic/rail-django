"""
DocumentationGenerator implementation.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..comparison import SchemaComparison
from ..schema_introspector import SchemaIntrospection
from .config import DocumentationConfig
from .markdown import MarkdownGeneratorMixin
from .html import HTMLGeneratorMixin
from .comparison import ComparisonGeneratorMixin

logger = logging.getLogger(__name__)


class DocumentationGenerator(MarkdownGeneratorMixin, HTMLGeneratorMixin, ComparisonGeneratorMixin):
    """
    Comprehensive GraphQL schema documentation generator.
    """

    def __init__(self, config: DocumentationConfig = None):
        self.config = config or DocumentationConfig()
        self.logger = logging.getLogger(__name__)

    def generate_markdown_documentation(self, introspection: SchemaIntrospection,
                                        output_path: Optional[str] = None) -> str:
        """Generate comprehensive Markdown documentation."""
        self.logger.info(f"Generating Markdown documentation for schema '{introspection.schema_name}'")
        content = []
        content.append(self._generate_markdown_header(introspection))
        if self.config.generate_toc: content.append(self._generate_markdown_toc(introspection))
        content.append(self._generate_markdown_overview(introspection))
        content.append(self._generate_markdown_root_types(introspection))
        content.append(self._generate_markdown_types(introspection))
        if self.config.include_directives and introspection.directives:
            content.append(self._generate_markdown_directives(introspection))
        if self.config.include_complexity_metrics:
            content.append(self._generate_markdown_complexity(introspection))
        markdown_content = '\n\n'.join(content)
        if output_path:
            Path(output_path).write_text(markdown_content, encoding='utf-8')
        return markdown_content

    def generate_html_documentation(self, introspection: SchemaIntrospection,
                                    output_path: Optional[str] = None) -> str:
        """Generate comprehensive HTML documentation."""
        self.logger.info(f"Generating HTML documentation for schema '{introspection.schema_name}'")
        markdown_content = self.generate_markdown_documentation(introspection)
        html_content = self._markdown_to_html(markdown_content, introspection)
        if output_path:
            Path(output_path).write_text(html_content, encoding='utf-8')
        return html_content

    def generate_json_documentation(self, introspection: SchemaIntrospection,
                                    output_path: Optional[str] = None) -> str:
        """Generate JSON documentation."""
        self.logger.info(f"Generating JSON documentation for schema '{introspection.schema_name}'")
        json_data = introspection.to_dict()
        json_content = json.dumps(json_data, indent=2, ensure_ascii=False)
        if output_path:
            Path(output_path).write_text(json_content, encoding='utf-8')
        return json_content

    def generate_comparison_report(self, comparison: SchemaComparison,
                                   output_path: Optional[str] = None,
                                   format: str = 'markdown') -> str:
        """Generate schema comparison report."""
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
        return content
