"""
Documentation generation package.

This package provides capabilities for generating comprehensive documentation
from GraphQL schema introspections, including HTML, Markdown, and JSON formats.
"""

from .config import DocumentationConfig
from .generator import DocumentationGenerator

__all__ = [
    "DocumentationConfig",
    "DocumentationGenerator",
]
