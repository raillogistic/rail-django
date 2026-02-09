"""Shared helpers for building GraphQL access control declarations."""

from typing import Dict, Iterable, Optional

from rail_django.core.meta import GraphQLMeta

OperationMap = Dict[str, GraphQLMeta.OperationGuard]

HISTORY_ROLE_NAME = "history_auditor"


def _build_history_role() -> GraphQLMeta.Role:
    return GraphQLMeta.Role(
        name=HISTORY_ROLE_NAME,
        description="Consulte tous les historiques métiers (lecture seule).",
        role_type="functional",
        permissions=["history.read"],
    )


HISTORY_AUDITOR_ROLES = [HISTORY_ROLE_NAME]


def include_history_role(
    roles: Dict[str, GraphQLMeta.Role],
) -> Dict[str, GraphQLMeta.Role]:
    """Ensure the shared history auditor role is registered alongside local roles."""

    combined = {**roles}
    if HISTORY_ROLE_NAME not in combined:
        combined[HISTORY_ROLE_NAME] = _build_history_role()
    return combined


def build_operation_guards(
    *,
    read_roles: Iterable[str],
    create_roles: Optional[Iterable[str]] = None,
    update_roles: Optional[Iterable[str]] = None,
    delete_roles: Optional[Iterable[str]] = None,
    history_roles: Optional[Iterable[str]] = None,
    extra: Optional[OperationMap] = None,
) -> OperationMap:
    """Create a default operation guard mapping for GraphQLMeta.

    Args:
        read_roles: Roles allowed to list/retrieve records (and base guard).
        create_roles: Optional roles allowed to create records.
        update_roles: Optional roles allowed to update records.
        delete_roles: Optional roles allowed to delete records.
        extra: Additional operation guards to merge in (approve, validate, etc.).
    """

    read_roles_list = list(read_roles)
    operations: OperationMap = {
        "*": GraphQLMeta.OperationGuard(
            roles=read_roles_list,
            require_authentication=True,
        ),
        "list": GraphQLMeta.OperationGuard(roles=read_roles_list),
        "retrieve": GraphQLMeta.OperationGuard(roles=read_roles_list),
    }

    if create_roles:
        operations["create"] = GraphQLMeta.OperationGuard(roles=list(create_roles))
    if update_roles:
        operations["update"] = GraphQLMeta.OperationGuard(roles=list(update_roles))
    if delete_roles:
        operations["delete"] = GraphQLMeta.OperationGuard(roles=list(delete_roles))
    if history_roles:
        operations["history"] = GraphQLMeta.OperationGuard(roles=list(history_roles))

    if extra:
        operations.update(extra)

    return operations
