from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self) -> None:
        """Register app-level field-permission overrides."""
        from rail_django.security.field_permissions import (
            FieldAccessLevel,
            FieldPermissionRule,
            FieldVisibility,
            field_permission_manager,
            is_owner_or_admin,
        )

        for model_name in ("users.user", "apps.users.user"):
            field_permission_manager.register_field_rule(
                FieldPermissionRule(
                    field_name="email",
                    model_name=model_name,
                    access_level=FieldAccessLevel.WRITE,
                    visibility=FieldVisibility.VISIBLE,
                    condition=is_owner_or_admin,
                )
            )
