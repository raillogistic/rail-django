"""
Schema export, history and diff views.
"""

from django.http import HttpRequest, JsonResponse
from .base import BaseAPIView
from rail_django.core.registry import schema_registry
from rail_django.core.schema_snapshots import get_schema_snapshot, list_schema_snapshots, get_schema_diff
from rail_django.config_proxy import get_setting

class SchemaExportAPIView(BaseAPIView):
    """API view for exporting schema snapshots or current schema."""
    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        if not get_setting("schema_registry.enable_schema_export", True, schema_name):
            return self.error_response("Schema export disabled", status=403)

        schema_info = schema_registry.get_schema(schema_name)
        if not schema_info: return self.error_response(f"Schema '{schema_name}' not found", status=404)

        export_format = str(request.GET.get("format", "json")).lower()
        version = request.GET.get("version") or request.GET.get("schema_version")
        snapshot = get_schema_snapshot(schema_name, version=str(version)) if version else None
        if version and snapshot is None: return self.error_response("Schema snapshot not found", status=404)

        if snapshot:
            schema_json, schema_sdl, schema_hash = snapshot.schema_json, snapshot.schema_sdl or "", snapshot.schema_hash
        else:
            try:
                builder = schema_registry.get_schema_builder(schema_name)
                schema = builder.get_schema()
                from rail_django.introspection.schema_introspector import SchemaIntrospector
                from graphql.utilities import print_schema
                import hashlib
                graphql_schema = getattr(schema, "graphql_schema", None)
                if graphql_schema is None: return self.error_response("Schema is not ready", status=500)
                introspection = SchemaIntrospector().introspect_schema(graphql_schema, schema_name, version=str(builder.get_schema_version()), description=schema_info.description)
                schema_json = introspection.to_dict()
                schema_sdl = print_schema(graphql_schema)
                schema_hash = hashlib.sha256(schema_sdl.encode("utf-8")).hexdigest()
            except Exception as exc: return self.error_response(f"Schema export failed: {exc}", status=500)

        if export_format == "sdl":
            return self.json_response({"schema_name": schema_name, "version": version or schema_info.version, "schema_hash": schema_hash, "sdl": schema_sdl})
        if export_format == "markdown":
            try:
                from rail_django.introspection.documentation import DocumentationGenerator
                from rail_django.introspection.schema_introspector import SchemaIntrospection
                markdown = DocumentationGenerator().generate_markdown_documentation(SchemaIntrospection.from_dict(schema_json))
                return self.json_response({"schema_name": schema_name, "version": version or schema_info.version, "schema_hash": schema_hash, "markdown": markdown})
            except Exception as exc: return self.error_response(f"Markdown export failed: {exc}", status=500)

        return self.json_response({"schema_name": schema_name, "version": version or schema_info.version, "schema_hash": schema_hash, "schema": schema_json})


class SchemaHistoryAPIView(BaseAPIView):
    """API view for schema snapshot history."""
    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        if not get_setting("schema_registry.enable_schema_snapshots", False, schema_name):
            return self.error_response("Schema snapshots disabled", status=403)
        limit = int(request.GET.get("limit", 10))
        snapshots = list_schema_snapshots(schema_name, limit=limit)
        history = [{"schema_name": s.schema_name, "version": s.version, "schema_hash": s.schema_hash, "created_at": s.created_at.isoformat() if s.created_at else None} for s in snapshots]
        return self.json_response({"history": history, "count": len(history)})


class SchemaDiffAPIView(BaseAPIView):
    """API view for diffing schema snapshots."""
    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        if not get_setting("schema_registry.enable_schema_diff", True, schema_name):
            return self.error_response("Schema diff disabled", status=403)
        from_v, to_v = request.GET.get("from_version"), request.GET.get("to_version")
        if from_v and to_v:
            from_snapshot, to_snapshot = get_schema_snapshot(schema_name, version=str(from_v)), get_schema_snapshot(schema_name, version=str(to_v))
        else:
            snapshots = list_schema_snapshots(schema_name, limit=2)
            if len(snapshots) < 2: return self.error_response("Not enough snapshots for diff", status=400)
            to_snapshot, from_snapshot = snapshots[0], snapshots[1]
        diff = get_schema_diff(from_snapshot, to_snapshot)
        if diff is None: return self.error_response("Schema diff failed", status=500)
        return self.json_response({"schema_name": schema_name, "from_version": getattr(from_snapshot, "version", None), "to_version": getattr(to_snapshot, "version", None), "diff": diff})
