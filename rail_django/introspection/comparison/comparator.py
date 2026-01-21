"""
SchemaComparator implementation.
"""

import logging
from typing import Any, List, Optional

from ..schema_introspector import FieldInfo, SchemaIntrospection, TypeInfo
from .types import BreakingChangeLevel, ChangeType, SchemaChange, SchemaComparison

logger = logging.getLogger(__name__)


class SchemaComparator:
    """
    Comprehensive GraphQL schema comparator.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.breaking_change_rules = {
            'type_removed': BreakingChangeLevel.CRITICAL, 'field_removed': BreakingChangeLevel.HIGH,
            'field_type_changed': BreakingChangeLevel.HIGH, 'argument_removed': BreakingChangeLevel.MEDIUM,
            'argument_type_changed': BreakingChangeLevel.MEDIUM, 'nullable_to_non_null': BreakingChangeLevel.HIGH,
            'list_to_non_list': BreakingChangeLevel.HIGH, 'enum_value_removed': BreakingChangeLevel.MEDIUM,
            'interface_removed': BreakingChangeLevel.HIGH, 'union_type_removed': BreakingChangeLevel.HIGH,
            'directive_removed': BreakingChangeLevel.LOW
        }

    def compare_schemas(self, old_schema: SchemaIntrospection,
                        new_schema: SchemaIntrospection) -> SchemaComparison:
        """Compare two schema introspections."""
        self.logger.info(f"Comparing schemas: {old_schema.schema_name} -> {new_schema.schema_name}")
        comparison = SchemaComparison(old_schema_name=old_schema.schema_name, new_schema_name=new_schema.schema_name, old_version=old_schema.version, new_version=new_schema.version)
        try:
            self._compare_types(old_schema, new_schema, comparison)
            self._compare_root_fields(old_schema, new_schema, comparison)
            self._compare_directives(old_schema, new_schema, comparison)
            self._calculate_summary(comparison)
            self._analyze_breaking_changes(comparison)
            self.logger.info(f"Schema comparison completed: {comparison.total_changes} changes found")
        except Exception as e:
            self.logger.error(f"Error during schema comparison: {e}"); raise
        return comparison

    def _compare_types(self, old_schema: SchemaIntrospection, new_schema: SchemaIntrospection, comparison: SchemaComparison):
        old_t, new_t = set(old_schema.types.keys()), set(new_schema.types.keys())
        for name in new_t - old_t:
            comparison.type_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='type', element_path=name, new_value=new_schema.types[name].kind, description=f"Type '{name}' was added"))
        for name in old_t - new_t:
            comparison.type_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='type', element_path=name, old_value=old_schema.types[name].kind, description=f"Type '{name}' was removed", breaking_level=self.breaking_change_rules.get('type_removed', BreakingChangeLevel.CRITICAL), migration_notes=f"All references to '{name}' must be updated"))
        for name in old_t & new_t:
            self._compare_type_details(old_schema.types[name], new_schema.types[name], comparison)

    def _compare_type_details(self, old_type: TypeInfo, new_type: TypeInfo, comparison: SchemaComparison):
        if old_type.kind != new_type.kind:
            comparison.type_changes.append(SchemaChange(change_type=ChangeType.MODIFIED, element_type='type', element_path=f"{old_type.name}.kind", old_value=old_type.kind, new_value=new_type.kind, description=f"Type '{old_type.name}' kind changed from {old_type.kind} to {new_type.kind}", breaking_level=BreakingChangeLevel.CRITICAL))
            return
        if old_type.kind in ['OBJECT', 'INTERFACE']: self._compare_fields(old_type, new_type, comparison)
        elif old_type.kind == 'ENUM': self._compare_enum_values(old_type, new_type, comparison)
        elif old_type.kind == 'INPUT_OBJECT': self._compare_input_fields(old_type, new_type, comparison)
        if old_type.kind == 'OBJECT': self._compare_interfaces(old_type, new_type, comparison)
        elif old_type.kind == 'UNION': self._compare_union_types(old_type, new_type, comparison)

    def _compare_fields(self, old_type: TypeInfo, new_type: TypeInfo, comparison: SchemaComparison):
        old_f = {f['name']: f for f in old_type.fields}; new_f = {f['name']: f for f in new_type.fields}
        old_n, new_n = set(old_f.keys()), set(new_f.keys())
        for n in new_n - old_n:
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='field', element_path=f"{old_type.name}.{n}", new_value=new_f[n]['type'], description=f"Field '{n}' was added"))
        for n in old_n - new_n:
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='field', element_path=f"{old_type.name}.{n}", old_value=old_f[n]['type'], description=f"Field '{n}' was removed", breaking_level=self.breaking_change_rules.get('field_removed', BreakingChangeLevel.HIGH)))
        for n in old_n & new_n:
            self._compare_field_details(old_type.name, old_f[n], new_f[n], comparison)

    def _compare_field_details(self, type_name: str, old_f: dict, new_f: dict, comparison: SchemaComparison):
        path = f"{type_name}.{old_f['name']}"
        if old_f['type'] != new_f['type']:
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.MODIFIED, element_type='field', element_path=f"{path}.type", old_value=old_f['type'], new_value=new_f['type'], description=f"Type changed to {new_f['type']}", breaking_level=self.breaking_change_rules.get('field_type_changed', BreakingChangeLevel.HIGH)))
        old_nl, new_nl = old_f.get('is_nullable', True), new_f.get('is_nullable', True)
        if old_nl and not new_nl:
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.MODIFIED, element_type='field', element_path=f"{path}.nullable", old_value=True, new_value=False, description="Became non-nullable", breaking_level=self.breaking_change_rules.get('nullable_to_non_null', BreakingChangeLevel.HIGH)))
        elif not old_nl and new_nl:
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.MODIFIED, element_type='field', element_path=f"{path}.nullable", old_value=False, new_value=True, description="Became nullable"))
        
        old_dep, new_dep = old_f.get('is_deprecated', False), new_f.get('is_deprecated', False)
        if not old_dep and new_dep: comparison.field_changes.append(SchemaChange(change_type=ChangeType.DEPRECATED, element_type='field', element_path=path, description=f"Deprecated: {new_f.get('deprecation_reason')}", breaking_level=BreakingChangeLevel.LOW))
        elif old_dep and not new_dep: comparison.field_changes.append(SchemaChange(change_type=ChangeType.UNDEPRECATED, element_type='field', element_path=path, description="No longer deprecated"))
        self._compare_arguments(path, old_f.get('args', []), new_f.get('args', []), comparison)

    def _compare_arguments(self, path: str, old_args: list, new_args: list, comparison: SchemaComparison):
        old_d = {a['name']: a for a in old_args}; new_d = {a['name']: a for a in new_args}
        old_n, new_n = set(old_d.keys()), set(new_d.keys())
        for n in new_n - old_n:
            lvl = BreakingChangeLevel.HIGH if '!' in new_d[n]['type'] else BreakingChangeLevel.NONE
            comparison.argument_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='argument', element_path=f"{path}({n})", new_value=new_d[n]['type'], description=f"Argument '{n}' added", breaking_level=lvl))
        for n in old_n - new_n:
            comparison.argument_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='argument', element_path=f"{path}({n})", old_value=old_d[n]['type'], description=f"Argument '{n}' removed", breaking_level=self.breaking_change_rules.get('argument_removed', BreakingChangeLevel.MEDIUM)))
        for n in old_n & new_n:
            if old_d[n]['type'] != new_d[n]['type']:
                comparison.argument_changes.append(SchemaChange(change_type=ChangeType.MODIFIED, element_type='argument', element_path=f"{path}({n})", old_value=old_d[n]['type'], new_value=new_d[n]['type'], description=f"Type changed to {new_d[n]['type']}", breaking_level=self.breaking_change_rules.get('argument_type_changed', BreakingChangeLevel.MEDIUM)))

    def _compare_enum_values(self, old_t: TypeInfo, new_type: TypeInfo, comparison: SchemaComparison):
        old_v = {v['name'] for v in old_t.enum_values}; new_v = {v['name'] for v in new_type.enum_values}
        for n in new_v - old_v: comparison.type_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='enum_value', element_path=f"{old_t.name}.{n}", description=f"Enum value '{n}' added"))
        for n in old_v - new_v: comparison.type_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='enum_value', element_path=f"{old_t.name}.{n}", description=f"Enum value '{n}' removed", breaking_level=self.breaking_change_rules.get('enum_value_removed', BreakingChangeLevel.MEDIUM)))

    def _compare_input_fields(self, old_t: TypeInfo, new_type: TypeInfo, comparison: SchemaComparison):
        old_f = {f['name']: f for f in old_t.input_fields}; new_f = {f['name']: f for f in new_type.input_fields}
        old_n, new_n = set(old_f.keys()), set(new_f.keys())
        for n in new_n - old_n:
            lvl = BreakingChangeLevel.HIGH if '!' in new_f[n]['type'] else BreakingChangeLevel.NONE
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='input_field', element_path=f"{old_t.name}.{n}", new_value=new_f[n]['type'], description=f"Input field '{n}' added", breaking_level=lvl))
        for n in old_n - new_n:
            comparison.field_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='input_field', element_path=f"{old_t.name}.{n}", old_value=old_f[n]['type'], description=f"Input field '{n}' removed", breaking_level=BreakingChangeLevel.MEDIUM))

    def _compare_interfaces(self, old_t: TypeInfo, new_type: TypeInfo, comparison: SchemaComparison):
        old_i, new_i = set(old_t.interfaces), set(new_type.interfaces)
        for n in old_i - new_i: comparison.type_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='interface', element_path=f"{old_t.name}.implements.{n}", description=f"No longer implements {n}", breaking_level=self.breaking_change_rules.get('interface_removed', BreakingChangeLevel.HIGH)))
        for n in new_i - old_i: comparison.type_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='interface', element_path=f"{old_t.name}.implements.{n}", description=f"Now implements {n}"))

    def _compare_union_types(self, old_t: TypeInfo, new_type: TypeInfo, comparison: SchemaComparison):
        old_p, new_p = set(old_t.possible_types), set(new_type.possible_types)
        for n in old_p - new_p: comparison.type_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='union_type', element_path=f"{old_t.name}.{n}", description=f"Removed from union", breaking_level=self.breaking_change_rules.get('union_type_removed', BreakingChangeLevel.HIGH)))
        for n in new_p - old_p: comparison.type_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='union_type', element_path=f"{old_t.name}.{n}", description="Added to union"))

    def _compare_root_fields(self, old_s: SchemaIntrospection, new_s: SchemaIntrospection, comparison: SchemaComparison):
        self._compare_root_field_list("Query", old_s.queries, new_s.queries, comparison)
        self._compare_root_field_list("Mutation", old_s.mutations, new_s.mutations, comparison)
        self._compare_root_field_list("Subscription", old_s.subscriptions, new_s.subscriptions, comparison)

    def _compare_root_field_list(self, root: str, old_f: list, new_f: list, comparison: SchemaComparison):
        old_d = {f.name: f for f in old_f}; new_d = {f.name: f for f in new_f}
        old_n, new_n = set(old_d.keys()), set(new_d.keys())
        for n in new_n - old_n: comparison.field_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='root_field', element_path=f"{root}.{n}", new_value=new_d[n].type, description=f"{root} field '{n}' added"))
        for n in old_n - new_n: comparison.field_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='root_field', element_path=f"{root}.{n}", old_value=old_d[n].type, description=f"{root} field '{n}' removed", breaking_level=self.breaking_change_rules.get('field_removed', BreakingChangeLevel.HIGH)))
        for n in old_n & new_n:
            of, nf = old_d[n], new_d[n]
            self._compare_field_details(root, {'name':of.name,'type':of.type,'args':of.args,'is_deprecated':of.is_deprecated,'deprecation_reason':of.deprecation_reason,'is_nullable':of.is_nullable}, {'name':nf.name,'type':nf.type,'args':nf.args,'is_deprecated':nf.is_deprecated,'deprecation_reason':nf.deprecation_reason,'is_nullable':nf.is_nullable}, comparison)

    def _compare_directives(self, old_s: SchemaIntrospection, new_s: SchemaIntrospection, comparison: SchemaComparison):
        old_d, new_d = set(old_s.directives.keys()), set(new_s.directives.keys())
        for n in new_d - old_d: comparison.directive_changes.append(SchemaChange(change_type=ChangeType.ADDED, element_type='directive', element_path=f"@{n}", description=f"Directive '@{n}' added"))
        for n in old_d - new_d: comparison.directive_changes.append(SchemaChange(change_type=ChangeType.REMOVED, element_type='directive', element_path=f"@{n}", description=f"Directive '@{n}' removed", breaking_level=self.breaking_change_rules.get('directive_removed', BreakingChangeLevel.LOW)))

    def _calculate_summary(self, comparison: SchemaComparison):
        all_c = comparison.get_all_changes()
        comparison.total_changes = len(all_c)
        breaking = [c for c in all_c if c.breaking_level != BreakingChangeLevel.NONE]
        comparison.breaking_changes = len(breaking)
        comparison.non_breaking_changes = comparison.total_changes - comparison.breaking_changes

    def _analyze_breaking_changes(self, comparison: SchemaComparison):
        breaking = comparison.get_breaking_changes()
        if not breaking:
            comparison.breaking_change_level, comparison.migration_required, comparison.compatibility_score = BreakingChangeLevel.NONE, False, 1.0
            return
        max_l = max(c.breaking_level for c in breaking)
        comparison.breaking_change_level = max_l
        comparison.migration_required = max_l in [BreakingChangeLevel.HIGH, BreakingChangeLevel.CRITICAL]
        weights = {BreakingChangeLevel.LOW: 0.1, BreakingChangeLevel.MEDIUM: 0.3, BreakingChangeLevel.HIGH: 0.6, BreakingChangeLevel.CRITICAL: 1.0}
        total_imp = sum(weights.get(c.breaking_level, 0) for c in breaking)
        comparison.compatibility_score = max(0.0, 1.0 - (total_imp / max(comparison.total_changes * 1.0, 1.0)))
