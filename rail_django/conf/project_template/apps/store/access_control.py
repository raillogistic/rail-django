"""Roles and GraphQL guards for the store domain."""

from typing import Dict, List, Optional

from rail_django.core.meta import GraphQLMeta


HISTORY_AUDITOR_ROLES: List[str] = ["store_auditor"]


def include_history_role(
    roles: Dict[str, GraphQLMeta.Role],
) -> Dict[str, GraphQLMeta.Role]:
    if "store_auditor" in roles:
        return roles
    enriched = dict(roles)
    enriched["store_auditor"] = GraphQLMeta.Role(
        name="store_auditor",
        description="Audit and history access for the store domain.",
        role_type="functional",
        permissions=["store.view_order", "store.view_product"],
    )
    return enriched


STORE_ROLES: Dict[str, GraphQLMeta.Role] = include_history_role(
    {
        "catalog_viewer": GraphQLMeta.Role(
            name="catalog_viewer",
            description="Read-only access to the catalog.",
            role_type="functional",
            permissions=["store.view_product"],
        ),
        "catalog_manager": GraphQLMeta.Role(
            name="catalog_manager",
            description="Manage catalog items.",
            role_type="business",
            parent_roles=["catalog_viewer"],
            permissions=[
                "store.view_product",
                "store.add_product",
                "store.change_product",
                "store.delete_product",
            ],
        ),
        "order_viewer": GraphQLMeta.Role(
            name="order_viewer",
            description="Read-only access to orders.",
            role_type="functional",
            permissions=["store.view_order"],
        ),
        "order_manager": GraphQLMeta.Role(
            name="order_manager",
            description="Create and update orders.",
            role_type="business",
            parent_roles=["order_viewer"],
            permissions=[
                "store.view_order",
                "store.add_order",
                "store.change_order",
            ],
        ),
        "order_admin": GraphQLMeta.Role(
            name="order_admin",
            description="Full control of orders.",
            role_type="system",
            parent_roles=["order_manager"],
            permissions=[
                "store.view_order",
                "store.add_order",
                "store.change_order",
                "store.delete_order",
                "store.view_risk_score",
                "store.view_customer_pii",
            ],
            is_system_role=True,
            max_users=5,
        ),
        "finance_analyst": GraphQLMeta.Role(
            name="finance_analyst",
            description="Access to financial details.",
            role_type="business",
            permissions=["store.view_order", "store.view_financials"],
        ),
    }
)


CATALOG_READ_ROLES: List[str] = ["catalog_viewer", "catalog_manager"]
CATALOG_WRITE_ROLES: List[str] = ["catalog_manager"]
CATALOG_MANAGER_ROLES: List[str] = ["catalog_manager"]

ORDER_READ_ROLES: List[str] = [
    "order_viewer",
    "order_manager",
    "order_admin",
    "finance_analyst",
]
ORDER_WRITE_ROLES: List[str] = ["order_manager", "order_admin"]
ORDER_MANAGER_ROLES: List[str] = ["order_admin"]


def build_operation_guards(
    *,
    read_roles: List[str],
    create_roles: List[str],
    update_roles: List[str],
    delete_roles: List[str],
    history_roles: Optional[List[str]] = None,
    read_permissions: Optional[List[str]] = None,
    create_permissions: Optional[List[str]] = None,
    update_permissions: Optional[List[str]] = None,
    delete_permissions: Optional[List[str]] = None,
    history_permissions: Optional[List[str]] = None,
    allow_anonymous_read: bool = False,
) -> Dict[str, GraphQLMeta.OperationGuard]:
    read_roles = list(read_roles or [])
    create_roles = list(create_roles or [])
    update_roles = list(update_roles or [])
    delete_roles = list(delete_roles or [])
    history_roles = list(history_roles or [])
    read_permissions = list(read_permissions or [])
    create_permissions = list(create_permissions or [])
    update_permissions = list(update_permissions or [])
    delete_permissions = list(delete_permissions or [])
    history_permissions = list(history_permissions or [])

    guards: Dict[str, GraphQLMeta.OperationGuard] = {
        "list": GraphQLMeta.OperationGuard(
            roles=read_roles,
            permissions=read_permissions,
            require_authentication=not allow_anonymous_read,
            allow_anonymous=allow_anonymous_read,
        ),
        "retrieve": GraphQLMeta.OperationGuard(
            roles=read_roles,
            permissions=read_permissions,
            require_authentication=not allow_anonymous_read,
            allow_anonymous=allow_anonymous_read,
        ),
        "create": GraphQLMeta.OperationGuard(
            roles=create_roles,
            permissions=create_permissions,
            require_authentication=True,
        ),
        "update": GraphQLMeta.OperationGuard(
            roles=update_roles,
            permissions=update_permissions,
            require_authentication=True,
        ),
        "delete": GraphQLMeta.OperationGuard(
            roles=delete_roles,
            permissions=delete_permissions,
            require_authentication=True,
        ),
    }

    if history_roles or history_permissions:
        guards["history"] = GraphQLMeta.OperationGuard(
            roles=history_roles,
            permissions=history_permissions,
            require_authentication=True,
        )

    return guards


def catalog_operations(*, allow_anonymous_read: bool = False):
    """Operations for catalog models (products, categories, tags)."""
    return build_operation_guards(
        read_roles=CATALOG_READ_ROLES,
        create_roles=CATALOG_WRITE_ROLES,
        update_roles=CATALOG_WRITE_ROLES,
        delete_roles=CATALOG_MANAGER_ROLES,
        history_roles=HISTORY_AUDITOR_ROLES,
        read_permissions=["store.view_product"],
        create_permissions=["store.add_product"],
        update_permissions=["store.change_product"],
        delete_permissions=["store.delete_product"],
        history_permissions=["store.view_product"],
        allow_anonymous_read=allow_anonymous_read,
    )


def order_operations():
    """Operations for orders and financial workflows."""
    guards = build_operation_guards(
        read_roles=ORDER_READ_ROLES,
        create_roles=ORDER_WRITE_ROLES,
        update_roles=ORDER_WRITE_ROLES,
        delete_roles=ORDER_MANAGER_ROLES,
        history_roles=HISTORY_AUDITOR_ROLES,
        read_permissions=["store.view_order"],
        create_permissions=["store.add_order"],
        update_permissions=["store.change_order"],
        delete_permissions=["store.delete_order"],
        history_permissions=["store.view_order"],
        allow_anonymous_read=False,
    )

    guards["retrieve"].condition = "can_access_order"
    guards["retrieve"].deny_message = "You do not have access to this order."
    guards["create"].deny_message = "Only order managers can create orders."
    guards["update"].condition = "can_modify_order"
    guards["update"].match = "all"
    guards["update"].deny_message = "Only assigned managers can update orders."
    guards["delete"].deny_message = "Only order admins can delete orders."
    return guards
