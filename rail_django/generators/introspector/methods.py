"""
Method analysis logic for ModelIntrospector.
"""

from typing import Any

class MethodAnalyzerMixin:
    """Mixin for analyzing model methods."""

    def _is_django_builtin_method(self, method_name: str, method: Any) -> bool:
        """Determines if a method is a Django model built-in method."""
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
        if hasattr(method, "_is_mutation"): return method._is_mutation
        if hasattr(method, "_is_business_logic"): return method._is_business_logic
        mutation_patterns = ["create", "update", "delete", "remove", "add", "set", "clear", "activate", "deactivate", "enable", "disable", "toggle", "approve", "reject", "publish", "unpublish", "archive", "process", "execute", "perform", "handle", "trigger", "send", "notify", "calculate", "generate", "sync"]
        method_lower = method_name.lower()
        if any(pattern in method_lower for pattern in mutation_patterns): return True
        if method.__doc__:
            doc_lower = method.__doc__.lower()
            if any(kw in doc_lower for kw in ["modify", "change", "update", "create", "delete", "save", "process", "execute"]): return True
        return False
