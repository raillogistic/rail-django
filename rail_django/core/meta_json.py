"""
Backward-compatible imports for app-level meta configuration helpers.
"""

from .meta.json_loader import clear_meta_configs, get_model_meta_config, load_app_meta_configs

__all__ = ["load_app_meta_configs", "get_model_meta_config", "clear_meta_configs"]
