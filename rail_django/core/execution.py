"""Operation-wide validation for the framework's GraphQL HTTP execution path."""

from graphql import ExecutionContext, MiddlewareManager, OperationType
from graphql.execution.collect_fields import collect_fields
from graphql.execution.execute import get_field_def
from graphql.pyutils import Path

from .middleware.performance import QueryComplexityMiddleware


def _validated_limits(protected, error):
    """Keep the original middleware position and per-field error contract."""

    def resolve(next_resolver, root, info, **kwargs):
        if info.path.prev is None and info.path.key in protected and error is not None:
            raise error.with_traceback(None)
        return next_resolver(root, info, **kwargs)

    return resolve


class RailExecutionContext(ExecutionContext):
    """Analyze document limits once per execution; retain all object/field checks."""

    def execute_operation(self, operation, root_value):
        manager = self.middleware_manager
        if manager is None:
            return super().execute_operation(operation, root_value)
        checkers = [
            mw for mw in manager.middlewares if type(mw) is QueryComplexityMiddleware
        ]
        if not checkers:
            return super().execute_operation(operation, root_value)

        replacements = {}
        root_type = self.schema.get_root_type(operation.operation)
        fields = None
        for checker in checkers:
            protected = {}
            error = None
            if (
                checker.settings.enable_query_complexity_middleware
                and operation.operation == OperationType.QUERY
            ):
                selectors = checker.limited_query_selectors()
                if fields is None and selectors and root_type:
                    fields = collect_fields(
                        self.schema,
                        self.fragments,
                        self.variable_values,
                        root_type,
                        operation.selection_set,
                    )
                operation_name = operation.name.value.lower() if operation.name else ""
                for alias, nodes in (fields or {}).items():
                    if (
                        operation_name in selectors
                        or nodes[0].name.value.lower() in selectors
                    ) and get_field_def(self.schema, root_type, nodes[0]) is not None:
                        protected[alias] = nodes
                if protected:
                    alias, nodes = next(iter(protected.items()))
                    field = get_field_def(self.schema, root_type, nodes[0])
                    info = self.build_resolve_info(
                        field, nodes, root_type, Path(None, alias, root_type.name)
                    )
                    try:
                        errors = checker.validate_operation(info)
                        if errors:
                            error = ValueError(
                                f"Query complexity validation failed: {'; '.join(errors)}"
                            )
                    except Exception as exc:
                        error = exc
            replacements[id(checker)] = (
                _validated_limits(protected, error) if error is not None else None
            )
        middlewares = []
        for middleware in manager.middlewares:
            replacement = replacements.get(id(middleware), middleware)
            if replacement is not None:
                middlewares.append(replacement)
        self.middleware_manager = MiddlewareManager(*middlewares)
        return super().execute_operation(operation, root_value)
