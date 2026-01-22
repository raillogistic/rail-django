"""
Data classes for schema introspection results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TypeInfo:
    """Information about a GraphQL type."""
    name: str
    kind: str  # 'OBJECT', 'INTERFACE', 'UNION', 'ENUM', 'SCALAR', 'INPUT_OBJECT'
    description: Optional[str] = None
    fields: list[dict[str, Any]] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    possible_types: list[str] = field(default_factory=list)  # For unions/interfaces
    enum_values: list[dict[str, Any]] = field(default_factory=list)
    input_fields: list[dict[str, Any]] = field(default_factory=list)
    is_deprecated: bool = False
    deprecation_reason: Optional[str] = None


@dataclass
class FieldInfo:
    """Information about a GraphQL field."""
    name: str
    type: str
    description: Optional[str] = None
    args: list[dict[str, Any]] = field(default_factory=list)
    is_deprecated: bool = False
    deprecation_reason: Optional[str] = None
    is_nullable: bool = True
    is_list: bool = False


@dataclass
class DirectiveInfo:
    """Information about a GraphQL directive."""
    name: str
    description: Optional[str] = None
    locations: list[str] = field(default_factory=list)
    args: list[dict[str, Any]] = field(default_factory=list)
    is_repeatable: bool = False


@dataclass
class SchemaComplexity:
    """Schema complexity metrics."""
    total_types: int = 0
    object_types: int = 0
    interface_types: int = 0
    union_types: int = 0
    enum_types: int = 0
    scalar_types: int = 0
    input_types: int = 0
    total_fields: int = 0
    total_arguments: int = 0
    max_depth: int = 0
    circular_references: list[str] = field(default_factory=list)
    deprecated_fields: int = 0


@dataclass
class SchemaIntrospection:
    """Complete schema introspection result."""
    schema_name: str
    version: Optional[str] = None
    description: Optional[str] = None
    introspection_date: datetime = field(default_factory=datetime.now)

    # Schema structure
    types: dict[str, TypeInfo] = field(default_factory=dict)
    queries: list[FieldInfo] = field(default_factory=list)
    mutations: list[FieldInfo] = field(default_factory=list)
    subscriptions: list[FieldInfo] = field(default_factory=list)
    directives: dict[str, DirectiveInfo] = field(default_factory=dict)

    # Metadata
    complexity: SchemaComplexity = field(default_factory=SchemaComplexity)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'schema_name': self.schema_name,
            'version': self.version,
            'description': self.description,
            'introspection_date': self.introspection_date.isoformat(),
            'types': {name: self._type_info_to_dict(type_info)
                      for name, type_info in self.types.items()},
            'queries': [self._field_info_to_dict(field) for field in self.queries],
            'mutations': [self._field_info_to_dict(field) for field in self.mutations],
            'subscriptions': [self._field_info_to_dict(field) for field in self.subscriptions],
            'directives': {name: self._directive_info_to_dict(directive)
                           for name, directive in self.directives.items()},
            'complexity': {
                'total_types': self.complexity.total_types,
                'object_types': self.complexity.object_types,
                'interface_types': self.complexity.interface_types,
                'union_types': self.complexity.union_types,
                'enum_types': self.complexity.enum_types,
                'scalar_types': self.complexity.scalar_types,
                'input_types': self.complexity.input_types,
                'total_fields': self.complexity.total_fields,
                'total_arguments': self.complexity.total_arguments,
                'max_depth': self.complexity.max_depth,
                'circular_references': self.complexity.circular_references,
                'deprecated_fields': self.complexity.deprecated_fields
            },
            'dependencies': self.dependencies,
            'tags': self.tags
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchemaIntrospection":
        """Rehydrate a SchemaIntrospection from a dictionary."""
        if not isinstance(data, dict):
            raise ValueError("SchemaIntrospection.from_dict expects a dict")

        complexity_data = data.get("complexity", {}) or {}
        complexity = SchemaComplexity(
            total_types=complexity_data.get("total_types", 0),
            object_types=complexity_data.get("object_types", 0),
            interface_types=complexity_data.get("interface_types", 0),
            union_types=complexity_data.get("union_types", 0),
            enum_types=complexity_data.get("enum_types", 0),
            scalar_types=complexity_data.get("scalar_types", 0),
            input_types=complexity_data.get("input_types", 0),
            total_fields=complexity_data.get("total_fields", 0),
            total_arguments=complexity_data.get("total_arguments", 0),
            max_depth=complexity_data.get("max_depth", 0),
            circular_references=complexity_data.get("circular_references", []) or [],
            deprecated_fields=complexity_data.get("deprecated_fields", 0),
        )

        introspection = cls(
            schema_name=data.get("schema_name", ""),
            version=data.get("version"),
            description=data.get("description"),
        )
        timestamp = data.get("introspection_date")
        if isinstance(timestamp, str):
            try:
                introspection.introspection_date = datetime.fromisoformat(timestamp)
            except ValueError:
                pass
        introspection.complexity = complexity

        types_data = data.get("types", {}) or {}
        for type_name, type_dict in types_data.items():
            introspection.types[type_name] = TypeInfo(
                name=type_dict.get("name", type_name),
                kind=type_dict.get("kind", ""),
                description=type_dict.get("description"),
                fields=type_dict.get("fields", []) or [],
                interfaces=type_dict.get("interfaces", []) or [],
                possible_types=type_dict.get("possible_types", []) or [],
                enum_values=type_dict.get("enum_values", []) or [],
                input_fields=type_dict.get("input_fields", []) or [],
                is_deprecated=bool(type_dict.get("is_deprecated", False)),
                deprecation_reason=type_dict.get("deprecation_reason"),
            )

        introspection.queries = [
            FieldInfo(**field) for field in (data.get("queries", []) or [])
        ]
        introspection.mutations = [
            FieldInfo(**field) for field in (data.get("mutations", []) or [])
        ]
        introspection.subscriptions = [
            FieldInfo(**field) for field in (data.get("subscriptions", []) or [])
        ]

        directives_data = data.get("directives", {}) or {}
        for name, directive in directives_data.items():
            introspection.directives[name] = DirectiveInfo(
                name=directive.get("name", name),
                description=directive.get("description"),
                locations=directive.get("locations", []) or [],
                args=directive.get("args", []) or [],
                is_repeatable=bool(directive.get("is_repeatable", False)),
            )

        introspection.dependencies = data.get("dependencies", []) or []
        introspection.tags = data.get("tags", []) or []
        return introspection

    def _type_info_to_dict(self, type_info: TypeInfo) -> dict[str, Any]:
        """Convert TypeInfo to dictionary."""
        return {
            'name': type_info.name,
            'kind': type_info.kind,
            'description': type_info.description,
            'fields': type_info.fields,
            'interfaces': type_info.interfaces,
            'possible_types': type_info.possible_types,
            'enum_values': type_info.enum_values,
            'input_fields': type_info.input_fields,
            'is_deprecated': type_info.is_deprecated,
            'deprecation_reason': type_info.deprecation_reason
        }

    def _field_info_to_dict(self, field_info: FieldInfo) -> dict[str, Any]:
        """Convert FieldInfo to dictionary."""
        return {
            'name': field_info.name,
            'type': field_info.type,
            'description': field_info.description,
            'args': field_info.args,
            'is_deprecated': field_info.is_deprecated,
            'deprecation_reason': field_info.deprecation_reason,
            'is_nullable': field_info.is_nullable,
            'is_list': field_info.is_list
        }

    def _directive_info_to_dict(self, directive_info: DirectiveInfo) -> dict[str, Any]:
        """Convert DirectiveInfo to dictionary."""
        return {
            'name': directive_info.name,
            'description': directive_info.description,
            'locations': directive_info.locations,
            'args': directive_info.args,
            'is_repeatable': directive_info.is_repeatable
        }
