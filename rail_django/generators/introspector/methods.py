"""
Method analysis logic for ModelIntrospector.
"""

from typing import Any

from ...utils.history_detection import is_historical_helper_method

class MethodAnalyzerMixin:
    """Mixin for analyzing model methods."""

    def _is_django_builtin_method(self, method_name: str, method: Any) -> bool:
        """Determines if a method is a Django model built-in method."""
        if is_historical_helper_method(self.model, method_name, method):
            return True

        django_builtin_methods = {
            "clean", "clean_fields", "full_clean", "validate_unique", "validate_constraints",
            "save", "save_base", "delete", "adelete", "refresh_from_db", "arefresh_from_db",
            "get_absolute_url", "get_deferred_fields", "serializable_value", "prepare_database_save",
            "unique_error_message", "date_error_message", "get_constraints", "asave",
        }
        polymorphic_methods = {"get_real_instance", "get_real_instance_class", "get_real_concrete_instance_class", "get_polymorphic_value", "polymorphic_super"}
        auto_generated_patterns = ["get_next_by_", "get_previous_by_", "get_", "_display"]

        if method_name in django_builtin_methods or method_name in polymorphic_methods: return True
        for pattern in auto_generated_patterns:
            if pattern in method_name:
                if method_name.endswith("_display"): return True
                if method_name.startswith(("get_next_by_", "get_previous_by_")): return True

        try:
            for cls in self.model.__mro__:
                if cls.__name__ in ["Model", "PolymorphicModel"] and hasattr(cls, method_name): return True
        except AttributeError: pass
        return False

    def _is_mutation_method(self, method_name: str, method: Any) -> bool:
        """Determines if a method is a mutation."""
        return bool(
            getattr(method, "_is_mutation", False)
            or getattr(method, "_is_business_logic", False)
        )
