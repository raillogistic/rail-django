"""
Query complexity visitor.
"""

from typing import Any, Optional
from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    InlineFragmentNode,
    Visitor,
)


class ComplexityVisitor(Visitor):
    """Visitor for calculating query complexity."""

    def __init__(self, field_complexity_map: dict[str, int] = None,
                 max_depth: int = 15, introspection_cost: int = 1):
        # Initialize parent Visitor class to set up enter_leave_map
        super().__init__()

        self.field_complexity_map = field_complexity_map or {}
        self.max_depth = max_depth
        self.introspection_cost = introspection_cost

        self.complexity = 0
        self.depth = 0
        self.max_depth_reached = 0
        self.field_count = 0
        self.fragment_count = 0
        self.field_path = []
        self.complexity_by_field = {}
        self.expensive_fields = []

    def enter_field(self, node: FieldNode, *_):
        """Enter a field node."""
        field_name = node.name.value
        self.field_count += 1
        self.depth += 1
        self.max_depth_reached = max(self.max_depth_reached, self.depth)

        # Build field path
        self.field_path.append(field_name)
        current_path = '.'.join(self.field_path)

        # Calculate field complexity
        field_complexity = self._calculate_field_complexity(node, current_path)
        self.complexity += field_complexity
        self.complexity_by_field[current_path] = field_complexity

        # Track expensive fields
        if field_complexity > 10:  # Configurable threshold
            self.expensive_fields.append(current_path)

        return node

    def leave_field(self, node: FieldNode, *_):
        """Leave a field node."""
        self.depth -= 1
        if self.field_path:
            self.field_path.pop()
        return node

    def enter_fragment_definition(self, node: FragmentDefinitionNode, *_):
        """Enter a fragment definition."""
        self.fragment_count += 1
        return node

    def enter_inline_fragment(self, node: InlineFragmentNode, *_):
        """Enter an inline fragment."""
        self.fragment_count += 1
        return node

    def _calculate_field_complexity(self, node: FieldNode, field_path: str) -> int:
        """Calculate complexity for a specific field."""
        field_name = node.name.value

        # Check if it's an introspection field
        if field_name.startswith('__'):
            return self.introspection_cost

        # Use configured complexity if available
        if field_path in self.field_complexity_map:
            base_complexity = self.field_complexity_map[field_path]
        elif field_name in self.field_complexity_map:
            base_complexity = self.field_complexity_map[field_name]
        else:
            # Default complexity based on field characteristics
            base_complexity = self._estimate_field_complexity(node)

        # Apply multipliers based on arguments
        multiplier = self._calculate_argument_multiplier(node)

        return int(base_complexity * multiplier)

    def _estimate_field_complexity(self, node: FieldNode) -> int:
        """Estimate field complexity based on characteristics."""
        field_name = node.name.value

        # List fields are generally more expensive
        if any(keyword in field_name.lower() for keyword in ['list', 'all', 'search', 'filter']):
            return 5

        # Relation fields
        if any(keyword in field_name.lower() for keyword in ['user', 'users', 'post', 'posts']):
            return 3

        # Simple scalar fields
        return 1

    def _calculate_argument_multiplier(self, node: FieldNode) -> float:
        """Calculate complexity multiplier based on field arguments."""
        if not node.arguments:
            return 1.0

        multiplier = 1.0

        for arg in node.arguments:
            arg_name = arg.name.value.lower()

            # Pagination arguments reduce complexity
            if arg_name in ['first', 'last', 'limit']:
                try:
                    if hasattr(arg.value, 'value'):
                        limit_value = int(arg.value.value)
                        # Cap the multiplier based on limit
                        multiplier *= min(limit_value / 10, 5.0)
                except (ValueError, AttributeError):
                    multiplier *= 2.0  # Unknown limit, assume moderate impact

            # Search/filter arguments increase complexity
            elif arg_name in ['search', 'filter', 'where']:
                multiplier *= 1.5

            # Sorting arguments add slight complexity
            elif arg_name in ['order_by', 'sort']:
                multiplier *= 1.2

        return multiplier
