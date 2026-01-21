"""
Configuration for documentation generation.
"""

from dataclasses import dataclass
from typing import Optional


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
    custom_templates: Optional[dict[str, str]] = None
