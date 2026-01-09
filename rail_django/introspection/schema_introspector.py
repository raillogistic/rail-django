"""
Schema introspection module.

This module provides comprehensive introspection capabilities for GraphQL schemas,
including detailed analysis of types, fields, directives, and schema complexity.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from graphql import (
    GraphQLArgument,
    GraphQLEnumType,
    GraphQLField,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLUnionType,
    get_named_type,
)
from graphql.execution import execute
from graphql.utilities import build_ast_schema, print_schema

logger = logging.getLogger(__name__)


@dataclass
class TypeInfo:
    """Information about a GraphQL type."""
    name: str
    kind: str  # 'OBJECT', 'INTERFACE', 'UNION', 'ENUM', 'SCALAR', 'INPUT_OBJECT'
    description: Optional[str] = None
    fields: List[Dict[str, Any]] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    possible_types: List[str] = field(default_factory=list)  # For unions/interfaces
    enum_values: List[Dict[str, Any]] = field(default_factory=list)
    input_fields: List[Dict[str, Any]] = field(default_factory=list)
    is_deprecated: bool = False
    deprecation_reason: Optional[str] = None


@dataclass
class FieldInfo:
    """Information about a GraphQL field."""
    name: str
    type: str
    description: Optional[str] = None
    args: List[Dict[str, Any]] = field(default_factory=list)
    is_deprecated: bool = False
    deprecation_reason: Optional[str] = None
    is_nullable: bool = True
    is_list: bool = False


@dataclass
class DirectiveInfo:
    """Information about a GraphQL directive."""
    name: str
    description: Optional[str] = None
    locations: List[str] = field(default_factory=list)
    args: List[Dict[str, Any]] = field(default_factory=list)
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
    circular_references: List[str] = field(default_factory=list)
    deprecated_fields: int = 0


@dataclass
class SchemaIntrospection:
    """Complete schema introspection result."""
    schema_name: str
    version: Optional[str] = None
    description: Optional[str] = None
    introspection_date: datetime = field(default_factory=datetime.now)

    # Schema structure
    types: Dict[str, TypeInfo] = field(default_factory=dict)
    queries: List[FieldInfo] = field(default_factory=list)
    mutations: List[FieldInfo] = field(default_factory=list)
    subscriptions: List[FieldInfo] = field(default_factory=list)
    directives: Dict[str, DirectiveInfo] = field(default_factory=dict)

    # Metadata
    complexity: SchemaComplexity = field(default_factory=SchemaComplexity)
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
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

    def _type_info_to_dict(self, type_info: TypeInfo) -> Dict[str, Any]:
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

    def _field_info_to_dict(self, field_info: FieldInfo) -> Dict[str, Any]:
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

    def _directive_info_to_dict(self, directive_info: DirectiveInfo) -> Dict[str, Any]:
        """Convert DirectiveInfo to dictionary."""
        return {
            'name': directive_info.name,
            'description': directive_info.description,
            'locations': directive_info.locations,
            'args': directive_info.args,
            'is_repeatable': directive_info.is_repeatable
        }


class SchemaIntrospector:
    """
    Comprehensive GraphQL schema introspector.

    Provides detailed analysis of GraphQL schemas including types, fields,
    directives, complexity metrics, and dependency analysis.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def introspect_schema(self, schema: GraphQLSchema, schema_name: str,
                          version: str = None, description: str = None,
                          additional_metadata: Dict[str, Any] = None) -> SchemaIntrospection:
        """
        Perform comprehensive schema introspection.

        Args:
            schema: GraphQL schema to introspect
            schema_name: Name of the schema
            version: Schema version
            description: Schema description
            additional_metadata: Additional metadata to include

        Returns:
            SchemaIntrospection with complete analysis
        """
        self.logger.info(f"Starting introspection for schema '{schema_name}'")

        introspection = SchemaIntrospection(
            schema_name=schema_name,
            version=version,
            description=description
        )

        try:
            # Introspect types
            self._introspect_types(schema, introspection)

            # Introspect root types
            self._introspect_root_types(schema, introspection)

            # Introspect directives
            self._introspect_directives(schema, introspection)

            # Calculate complexity metrics
            self._calculate_complexity(schema, introspection)

            # Extract dependencies
            self._extract_dependencies(schema, introspection, additional_metadata)

            self.logger.info(f"Introspection completed for schema '{schema_name}': "
                             f"{introspection.complexity.total_types} types, "
                             f"{introspection.complexity.total_fields} fields")

        except Exception as e:
            self.logger.error(f"Error during schema introspection: {e}")
            raise

        return introspection

    def _introspect_types(self, schema: GraphQLSchema, introspection: SchemaIntrospection):
        """Introspect all types in the schema."""
        type_map = schema.type_map

        for type_name, type_obj in type_map.items():
            # Skip introspection types
            if type_name.startswith('__'):
                continue

            type_info = self._analyze_type(type_obj)
            introspection.types[type_name] = type_info

    def _analyze_type(self, type_obj) -> TypeInfo:
        """Analyze a single GraphQL type."""
        type_info = TypeInfo(
            name=type_obj.name,
            kind=self._get_type_kind(type_obj),
            description=getattr(type_obj, 'description', None)
        )

        if isinstance(type_obj, GraphQLObjectType):
            self._analyze_object_type(type_obj, type_info)
        elif isinstance(type_obj, GraphQLInterfaceType):
            self._analyze_interface_type(type_obj, type_info)
        elif isinstance(type_obj, GraphQLUnionType):
            self._analyze_union_type(type_obj, type_info)
        elif isinstance(type_obj, GraphQLEnumType):
            self._analyze_enum_type(type_obj, type_info)
        elif isinstance(type_obj, GraphQLInputObjectType):
            self._analyze_input_type(type_obj, type_info)

        return type_info

    def _get_type_kind(self, type_obj) -> str:
        """Get the kind of a GraphQL type."""
        if isinstance(type_obj, GraphQLObjectType):
            return 'OBJECT'
        elif isinstance(type_obj, GraphQLInterfaceType):
            return 'INTERFACE'
        elif isinstance(type_obj, GraphQLUnionType):
            return 'UNION'
        elif isinstance(type_obj, GraphQLEnumType):
            return 'ENUM'
        elif isinstance(type_obj, GraphQLScalarType):
            return 'SCALAR'
        elif isinstance(type_obj, GraphQLInputObjectType):
            return 'INPUT_OBJECT'
        else:
            return 'UNKNOWN'

    def _analyze_object_type(self, type_obj: GraphQLObjectType, type_info: TypeInfo):
        """Analyze a GraphQL object type."""
        # Extract fields
        for field_name, field_obj in type_obj.fields.items():
            field_info = self._analyze_field(field_obj, field_name)
            type_info.fields.append(field_info.__dict__)

        # Extract interfaces
        if hasattr(type_obj, 'interfaces'):
            type_info.interfaces = [interface.name for interface in type_obj.interfaces]

    def _analyze_interface_type(self, type_obj: GraphQLInterfaceType, type_info: TypeInfo):
        """Analyze a GraphQL interface type."""
        # Extract fields
        for field_name, field_obj in type_obj.fields.items():
            field_info = self._analyze_field(field_obj, field_name)
            type_info.fields.append(field_info.__dict__)

    def _analyze_union_type(self, type_obj: GraphQLUnionType, type_info: TypeInfo):
        """Analyze a GraphQL union type."""
        if hasattr(type_obj, 'types'):
            type_info.possible_types = [union_type.name for union_type in type_obj.types]

    def _analyze_enum_type(self, type_obj: GraphQLEnumType, type_info: TypeInfo):
        """Analyze a GraphQL enum type."""
        for value_name, enum_value in type_obj.values.items():
            enum_info = {
                'name': value_name,
                'description': getattr(enum_value, 'description', None),
                'is_deprecated': getattr(enum_value, 'deprecation_reason', None) is not None,
                'deprecation_reason': getattr(enum_value, 'deprecation_reason', None)
            }
            type_info.enum_values.append(enum_info)

    def _analyze_input_type(self, type_obj: GraphQLInputObjectType, type_info: TypeInfo):
        """Analyze a GraphQL input object type."""
        for field_name, field_obj in type_obj.fields.items():
            field_info = {
                'name': field_name,
                'type': str(field_obj.type),
                'description': getattr(field_obj, 'description', None),
                'default_value': getattr(field_obj, 'default_value', None)
            }
            type_info.input_fields.append(field_info)

    def _analyze_field(self, field_obj: GraphQLField, field_name: str) -> FieldInfo:
        """Analyze a GraphQL field."""
        field_type = field_obj.type
        is_nullable = not isinstance(field_type, GraphQLNonNull)
        is_list = isinstance(field_type, GraphQLList) or (isinstance(
            field_type, GraphQLNonNull) and isinstance(field_type.of_type, GraphQLList))

        # Get the named type
        named_type = get_named_type(field_type)
        type_name = named_type.name if named_type else str(field_type)

        field_info = FieldInfo(
            name=field_name,
            type=type_name,
            description=getattr(field_obj, 'description', None),
            is_deprecated=getattr(field_obj, 'deprecation_reason', None) is not None,
            deprecation_reason=getattr(field_obj, 'deprecation_reason', None),
            is_nullable=is_nullable,
            is_list=is_list
        )

        # Extract arguments
        if hasattr(field_obj, 'args') and field_obj.args:
            for arg_name, arg_obj in field_obj.args.items():
                arg_info = {
                    'name': arg_name,
                    'type': str(arg_obj.type),
                    'description': getattr(arg_obj, 'description', None),
                    'default_value': getattr(arg_obj, 'default_value', None)
                }
                field_info.args.append(arg_info)

        return field_info

    def _introspect_root_types(self, schema: GraphQLSchema, introspection: SchemaIntrospection):
        """Introspect root types (Query, Mutation, Subscription)."""
        # Query type
        if schema.query_type:
            for field_name, field_obj in schema.query_type.fields.items():
                field_info = self._analyze_field(field_obj, field_name)
                introspection.queries.append(field_info)

        # Mutation type
        if schema.mutation_type:
            for field_name, field_obj in schema.mutation_type.fields.items():
                field_info = self._analyze_field(field_obj, field_name)
                introspection.mutations.append(field_info)

        # Subscription type
        if schema.subscription_type:
            for field_name, field_obj in schema.subscription_type.fields.items():
                field_info = self._analyze_field(field_obj, field_name)
                introspection.subscriptions.append(field_info)

    def _introspect_directives(self, schema: GraphQLSchema, introspection: SchemaIntrospection):
        """Introspect schema directives."""
        for directive in schema.directives:
            # Skip built-in directives
            if directive.name in ['skip', 'include', 'deprecated']:
                continue

            directive_info = DirectiveInfo(
                name=directive.name,
                description=getattr(directive, 'description', None),
                locations=[str(loc) for loc in directive.locations],
                is_repeatable=getattr(directive, 'is_repeatable', False)
            )

            # Extract arguments
            if hasattr(directive, 'args') and directive.args:
                for arg_name, arg_obj in directive.args.items():
                    arg_info = {
                        'name': arg_name,
                        'type': str(arg_obj.type),
                        'description': getattr(arg_obj, 'description', None),
                        'default_value': getattr(arg_obj, 'default_value', None)
                    }
                    directive_info.args.append(arg_info)

            introspection.directives[directive.name] = directive_info

    def _calculate_complexity(self, schema: GraphQLSchema, introspection: SchemaIntrospection):
        """Calculate schema complexity metrics."""
        complexity = introspection.complexity

        # Count types by kind
        for type_info in introspection.types.values():
            complexity.total_types += 1

            if type_info.kind == 'OBJECT':
                complexity.object_types += 1
            elif type_info.kind == 'INTERFACE':
                complexity.interface_types += 1
            elif type_info.kind == 'UNION':
                complexity.union_types += 1
            elif type_info.kind == 'ENUM':
                complexity.enum_types += 1
            elif type_info.kind == 'SCALAR':
                complexity.scalar_types += 1
            elif type_info.kind == 'INPUT_OBJECT':
                complexity.input_types += 1

            # Count fields and arguments
            complexity.total_fields += len(type_info.fields)
            for field in type_info.fields:
                complexity.total_arguments += len(field.get('args', []))
                if field.get('is_deprecated', False):
                    complexity.deprecated_fields += 1

        # Count root type fields
        complexity.total_fields += len(introspection.queries)
        complexity.total_fields += len(introspection.mutations)
        complexity.total_fields += len(introspection.subscriptions)

        # Calculate max depth (simplified)
        complexity.max_depth = self._calculate_max_depth(schema)

        # Detect circular references (simplified)
        complexity.circular_references = self._detect_circular_references(schema)

    def _calculate_max_depth(self, schema: GraphQLSchema) -> int:
        """Calculate maximum possible query depth (simplified)."""
        # This is a simplified implementation
        # A full implementation would traverse the type graph
        return min(10, len(schema.type_map) // 5)  # Rough estimate

    def _detect_circular_references(self, schema: GraphQLSchema) -> List[str]:
        """Detect circular references in schema (simplified)."""
        # This is a simplified implementation
        # A full implementation would perform graph traversal
        circular_refs = []

        # Basic check for self-referencing types
        for type_name, type_obj in schema.type_map.items():
            if type_name.startswith('__'):
                continue

            if isinstance(type_obj, GraphQLObjectType):
                for field_name, field_obj in type_obj.fields.items():
                    field_type = get_named_type(field_obj.type)
                    if field_type and field_type.name == type_name:
                        circular_refs.append(f"{type_name}.{field_name}")

        return circular_refs

    def _extract_dependencies(self, schema: GraphQLSchema, introspection: SchemaIntrospection,
                              additional_metadata: Dict[str, Any] = None):
        """Extract schema dependencies and metadata."""
        if additional_metadata:
            # Extract dependencies from metadata
            introspection.dependencies = additional_metadata.get('dependencies', [])
            introspection.tags = additional_metadata.get('tags', [])

        # Auto-detect some dependencies based on type names
        auto_dependencies = set()
        for type_name in introspection.types.keys():
            if 'user' in type_name.lower():
                auto_dependencies.add('authentication')
            elif 'product' in type_name.lower() or 'order' in type_name.lower():
                auto_dependencies.add('e-commerce')
            elif 'file' in type_name.lower() or 'image' in type_name.lower():
                auto_dependencies.add('media')

        introspection.dependencies.extend(list(auto_dependencies))
        introspection.dependencies = list(set(introspection.dependencies))  # Remove duplicates
