"""
Security configuration for the BI reporting module.

This module contains role and operation guard definitions for
the reporting extension's access control.
"""

from __future__ import annotations

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase


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
    return {
        "list": GraphQLMetaBase.OperationGuard(
            name="list",
            roles=["reporting_viewer", "reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "retrieve": GraphQLMetaBase.OperationGuard(
            name="retrieve",
            roles=["reporting_viewer", "reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "create": GraphQLMetaBase.OperationGuard(
            name="create",
            roles=["reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "update": GraphQLMetaBase.OperationGuard(
            name="update",
            roles=["reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "delete": GraphQLMetaBase.OperationGuard(
            name="delete",
            roles=["reporting_admin"],
            permissions=[],
        ),
    }


__all__ = [
    "_reporting_roles",
    "_reporting_operations",
]
