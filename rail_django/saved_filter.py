from django.conf import settings
from django.db import models
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta


class SavedFilter(models.Model):
    """
    Stores a reusable filter configuration for a specific GraphQL model.
    """
    name = models.CharField(max_length=100)
    model_name = models.CharField(
        max_length=100,
        help_text="The GraphQL type/model name this filter applies to (e.g. 'Order')"
    )
    filter_json = models.JSONField(
        help_text="The JSON representation of the where clause"
    )
    description = models.TextField(blank=True)
    
    # Ownership & Visibility
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_filters"
    )
    is_shared = models.BooleanField(
        default=False,
        help_text="If true, other users can see and use this filter"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "rail_django"
        unique_together = [("name", "created_by", "model_name")]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.model_name})"

    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(
            read_only=["created_at", "updated_at", "last_used_at", "use_count", "created_by"],
        )
        filtering = RailGraphQLMeta.Filtering(
            quick=["name", "description", "model_name"],
            fields={
                "model_name": {"lookups": ["eq", "in"]},
                "is_shared": {"lookups": ["eq"]},
            }
        )
        access = RailGraphQLMeta.AccessControl(
            operations={
                "create": RailGraphQLMeta.OperationGuard(require_authentication=True),
                "update": RailGraphQLMeta.OperationGuard(condition="is_owner"),
                "delete": RailGraphQLMeta.OperationGuard(condition="is_owner"),
                "list": RailGraphQLMeta.OperationGuard(require_authentication=True),
                "retrieve": RailGraphQLMeta.OperationGuard(condition="can_view"),
            }
        )

    @staticmethod
    def is_owner(user, operation, info, instance, model):
        if not user or not user.is_authenticated:
            return False
        return instance.created_by_id == user.id

    @staticmethod
    def can_view(user, operation, info, instance, model):
        if not user or not user.is_authenticated:
            return False
        if instance.is_shared:
            return True
        return instance.created_by_id == user.id
