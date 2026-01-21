"""
Export logic for SchemaManager.
"""

import json
from datetime import datetime

class SchemaExportMixin:
    """Mixin for exporting schemas."""

    def export_schemas(self, format: str = 'json', include_sdl: bool = False) -> str:
        """Export schema metadata and optionally SDL."""
        export_data = {'export_timestamp': datetime.now().isoformat(), 'schemas': []}
        with self._lock:
            for name, metadata in self._metadata.items():
                schema_data = {
                    'name': metadata.name, 'version': metadata.version, 'description': metadata.description,
                    'status': metadata.status.value, 'created_at': metadata.created_at.isoformat(),
                    'updated_at': metadata.updated_at.isoformat(), 'created_by': metadata.created_by,
                    'updated_by': metadata.updated_by, 'tags': metadata.tags, 'dependencies': metadata.dependencies
                }
                if metadata.deprecation_date: schema_data['deprecation_date'] = metadata.deprecation_date.isoformat()
                if metadata.migration_path: schema_data['migration_path'] = metadata.migration_path
                if include_sdl and name in self._schemas:
                    from graphql import print_schema
                    schema_data['sdl'] = print_schema(self._schemas[name])
                export_data['schemas'].append(schema_data)

        if format == 'json': return json.dumps(export_data, indent=2, ensure_ascii=False)
        elif format == 'yaml':
            import yaml
            return yaml.dump(export_data, default_flow_style=False)
        else: raise ValueError(f"Unsupported export format: {format}")
