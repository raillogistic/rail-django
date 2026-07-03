"""
Security configuration for the BI reporting module.

This module contains role and operation guard definitions for
the reporting extension's access control.
"""

from __future__ import annotations

from django.conf import settings

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.security.rbac import role_manager


def _configured_roles(key: str) -> list[str]:
    config = getattr(settings, "RAIL_DJANGO_REPORTING", {}) or {}
    return list(config.get(key, []))


def reporting_user_roles(user) -> set[str]:
    """Return directly assigned reporting/business roles for a user."""
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    return set(role_manager.get_user_roles(user))


def dataset_is_visible_to_user(dataset, user) -> bool:
    """Enforce a dataset's optional role allowlist."""
    if getattr(user, "is_superuser", False):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    allowed = set(
        getattr(dataset, "allowed_roles", None)
        or (dataset.metadata or {}).get("allowed_roles")
        or []
    )
    return not allowed or bool(allowed & reporting_user_roles(user))


def report_is_visible_to_user(report, user) -> bool:
    """Require report audience access and access to every backing dataset."""
    if getattr(user, "is_superuser", False):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    allowed = set(getattr(report, "allowed_roles", None) or [])
    if allowed and not allowed.intersection(reporting_user_roles(user)):
        return False
    blocks = list(report.blocks.all())
    return bool(blocks) and all(
        dataset_is_visible_to_user(block.visualization.dataset, user)
        for block in blocks
    )


def _reporting_roles() -> dict[str, GraphQLMetaBase.Role]:
    """
    Define the roles available for the reporting extension.

    Returns a dictionary mapping role names to Role instances with
    their permissions and parent role hierarchy.
    """
    return {
        "reporting_admin": GraphQLMetaBase.Role(
            name="reporting_admin",
            description="Administrateur BI (modeles, exports, securite)",
            permissions=[
                "rail_django.add_reportingdataset",
                "rail_django.change_reportingdataset",
                "rail_django.delete_reportingdataset",
                "rail_django.view_reportingdataset",
            ],
            parent_roles=[],
        ),
        "reporting_author": GraphQLMetaBase.Role(
            name="reporting_author",
            description="Concepteur de rapports (datasets et visuels)",
            permissions=[
                "rail_django.add_reportingdataset",
                "rail_django.change_reportingdataset",
                "rail_django.view_reportingdataset",
                "rail_django.add_reportingvisualization",
                "rail_django.change_reportingvisualization",
                "rail_django.view_reportingvisualization",
            ],
            parent_roles=["reporting_admin"],
        ),
        "reporting_viewer": GraphQLMetaBase.Role(
            name="reporting_viewer",
            description="Consultation des rapports et exports",
            permissions=[
                "rail_django.view_reportingdataset",
                "rail_django.view_reportingvisualization",
                "rail_django.view_reportingreport",
            ],
            parent_roles=["reporting_author"],
        ),
    }


def _reporting_operations() -> dict[str, GraphQLMetaBase.OperationGuard]:
    """
    Define the operation guards for the reporting extension.

    Returns a dictionary mapping operation names to OperationGuard instances
    with their allowed roles and required permissions.
    """
    viewer_roles = [
        "reporting_viewer",
        "reporting_author",
        "reporting_admin",
        *_configured_roles("viewer_roles"),
    ]
    author_roles = [
        "reporting_author",
        "reporting_admin",
        *_configured_roles("author_roles"),
    ]
    admin_roles = ["reporting_admin", *_configured_roles("admin_roles")]
    return {
        "list": GraphQLMetaBase.OperationGuard(
            name="list",
            roles=viewer_roles,
            permissions=[],
        ),
        "retrieve": GraphQLMetaBase.OperationGuard(
            name="retrieve",
            roles=viewer_roles,
            permissions=[],
        ),
        "create": GraphQLMetaBase.OperationGuard(
            name="create",
            roles=author_roles,
            permissions=[],
        ),
        "update": GraphQLMetaBase.OperationGuard(
            name="update",
            roles=author_roles,
            permissions=[],
        ),
        "delete": GraphQLMetaBase.OperationGuard(
            name="delete",
            roles=admin_roles,
            permissions=[],
        ),
    }


def _reporting_export_operations() -> dict[str, GraphQLMetaBase.OperationGuard]:
    """Allow viewers to create and run only their own export jobs."""
    operations = _reporting_operations()
    operations["create"] = GraphQLMetaBase.OperationGuard(
        name="create",
        roles=[
            "reporting_viewer",
            "reporting_author",
            "reporting_admin",
            *_configured_roles("viewer_roles"),
        ],
        permissions=[],
    )
    operations["update"] = operations["create"]
    return operations


__all__ = [
    "_reporting_roles",
    "_reporting_operations",
    "_reporting_export_operations",
    "dataset_is_visible_to_user",
    "report_is_visible_to_user",
    "reporting_user_roles",
]
