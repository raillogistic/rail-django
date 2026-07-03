"""Secure, metadata-driven authoring service for reporting assets."""

from __future__ import annotations

import re
from typing import Any

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils.text import slugify

from rail_django.extensions.metadata import (
    get_model_schema_for_user,
    list_available_models_for_user,
)
from rail_django.security.rbac import role_manager

from .models import (
    ReportingDataset,
    ReportingReport,
    ReportingReportBlock,
    ReportingVisualization,
)
from .security import reporting_user_roles
from .types import SAFE_BUILTINS, SAFE_QUERY_BUILTINS, ReportingError
from .visualization_registry import get_available_types, get_visualization_type

SUPPORTED_AGGREGATIONS = {"count", "distinct_count", "sum", "avg", "min", "max"}
SUPPORTED_TRANSFORMS = {
    "",
    "lower",
    "upper",
    "date",
    "year",
    "quarter",
    "month",
    "day",
    "week",
    "weekday",
    "trunc:hour",
    "trunc:day",
    "trunc:week",
    "trunc:month",
    "trunc:quarter",
    "trunc:year",
}
SUPPORTED_LOOKUPS = {
    "exact",
    "iexact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "in",
    "range",
    "isnull",
    "gt",
    "gte",
    "lt",
    "lte",
}
SUPPORTED_WIDTHS = {3, 4, 6, 8, 12}
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _reporting_config() -> dict:
    return getattr(settings, "RAIL_DJANGO_REPORTING", {}) or {}


class ReportingStudioService:
    """Validate and persist studio assets without exposing ORM paths directly."""

    def __init__(self, context: Any):
        self.context = context
        self.user = getattr(context, "user", None)
        self._require_author()

    def _author_roles(self) -> set[str]:
        config = _reporting_config()
        return {
            "reporting_author",
            "reporting_admin",
            *config.get("author_roles", []),
            *config.get("admin_roles", []),
        }

    def _require_author(self) -> None:
        if not self.user or not getattr(self.user, "is_authenticated", False):
            raise ReportingError("Authentification requise.")
        if getattr(self.user, "is_superuser", False):
            return
        if not self._author_roles().intersection(reporting_user_roles(self.user)):
            raise ReportingError("Un role auteur de rapports est requis.")

    def _roles(self, values: list[str] | None) -> list[str]:
        roles = {str(value).strip() for value in values or [] if str(value).strip()}
        known = set(Group.objects.filter(name__in=roles).values_list("name", flat=True))
        known.update(name for name in roles if role_manager.get_role_definition(name))
        unknown = roles - known
        if unknown:
            raise ReportingError(f"Roles inconnus: {', '.join(sorted(unknown))}")
        return sorted(roles | (self._author_roles() & reporting_user_roles(self.user)))

    @staticmethod
    def _identifier(value: Any, label: str) -> str:
        value = str(value or "").strip()
        if not IDENTIFIER.fullmatch(value):
            raise ReportingError(f"{label}: identifiant invalide.")
        return value

    @staticmethod
    def _unique_code(
        model, prefix: str, title: str, requested: str = "", **filters
    ) -> str:
        suffix = slugify(requested or title).replace("-", "_") or "rapport"
        base = f"{prefix}{suffix}"[:80]
        code = base
        index = 2
        queryset = model.objects.filter(**filters)
        while queryset.filter(code=code).exists():
            marker = f"_{index}"
            code = f"{base[:80 - len(marker)]}{marker}"
            index += 1
        return code

    def _schema(self, app_label: str, model_name: str) -> dict:
        try:
            return get_model_schema_for_user(app_label, model_name, self.user)
        except Exception as exc:
            raise ReportingError(
                f"Modele non autorise: {app_label}.{model_name}"
            ) from exc

    def _path_info(self, app_label: str, model_name: str, path: str) -> dict:
        parts = [part for part in str(path).split("__") if part]
        if not parts or len(parts) > 3:
            raise ReportingError(f"Champ non autorise: {path}")
        current_app, current_model = app_label, model_name
        for index, part in enumerate(parts):
            contract = self._schema(current_app, current_model)
            fields = {
                item.get("field_name", item.get("name")): item
                for item in contract.get("fields", [])
                if item.get("readable", False)
            }
            relations = {
                item.get("field_name", item.get("name")): item
                for item in contract.get("relationships", [])
                if item.get("readable", False)
            }
            last = index == len(parts) - 1
            if last and part in fields:
                return fields[part]
            if last and part.endswith("_id") and part[:-3] in relations:
                return {"field_name": part, "is_numeric": True, "is_relation_id": True}
            relation = relations.get(part)
            if not relation:
                raise ReportingError(f"Champ non lisible dans metadata: {path}")
            if last:
                return relation
            current_app = relation.get("related_app")
            current_model = relation.get("related_model")
        raise ReportingError(f"Champ non autorise: {path}")

    def _filter(self, item: dict, app_label: str, model_name: str) -> dict:
        field = str(item.get("field") or "")
        lookup = str(item.get("lookup") or "exact").lower()
        self._path_info(app_label, model_name, field)
        if lookup not in SUPPORTED_LOOKUPS:
            raise ReportingError(f"Operateur non autorise: {lookup}")
        return {"field": field, "lookup": lookup, "value": item.get("value")}

    @staticmethod
    def _dataset_fields(dataset: ReportingDataset) -> set[str]:
        return {
            item.get("field") for item in dataset.dimensions if item.get("field")
        } | set((dataset.metadata or {}).get("record_fields") or [])

    @staticmethod
    def _dataset_record_fields(dataset: ReportingDataset) -> list[str]:
        fields = set((dataset.metadata or {}).get("record_fields") or [])
        for visualization in dataset.visualizations.all():
            query = (visualization.config or {}).get("query") or {}
            fields.update(query.get("fields") or [])
        return sorted(fields)

    def build_dataset(self, data: dict) -> ReportingDataset:
        """Validate input and return an unsaved dataset instance."""
        existing = (
            ReportingDataset.objects.get(pk=data["id"]) if data.get("id") else None
        )
        app_label = str(data.get("source_app_label") or "").strip()
        model_name = str(data.get("source_model") or "").strip()
        self._schema(app_label, model_name)
        model = apps.get_model(app_label, model_name)

        dimensions, names = [], set()
        for item in data.get("dimensions") or []:
            name = self._identifier(item.get("name"), "Dimension")
            if name in names:
                raise ReportingError(f"Dimension dupliquee: {name}")
            names.add(name)
            field = str(item.get("field") or "")
            self._path_info(app_label, model_name, field)
            transform = str(item.get("transform") or "").lower()
            if transform not in SUPPORTED_TRANSFORMS:
                raise ReportingError(f"Transformation non autorisee: {transform}")
            dimensions.append(
                {
                    "name": name,
                    "field": field,
                    "label": str(item.get("label") or name),
                    **({"transform": transform} if transform else {}),
                }
            )
        if len(dimensions) > 50:
            raise ReportingError("Un dataset est limite a 50 dimensions.")

        metrics, metric_names = [], set()
        for item in data.get("metrics") or []:
            name = self._identifier(item.get("name"), "Mesure")
            if name in metric_names:
                raise ReportingError(f"Mesure dupliquee: {name}")
            metric_names.add(name)
            field = str(item.get("field") or "")
            info = self._path_info(app_label, model_name, field)
            aggregation = str(item.get("aggregation") or "sum").lower()
            if aggregation not in SUPPORTED_AGGREGATIONS:
                raise ReportingError(f"Agregation non autorisee: {aggregation}")
            if aggregation in {"sum", "avg"} and not info.get("is_numeric", False):
                raise ReportingError(f"La mesure {name} exige un champ numerique.")
            metrics.append(
                {
                    "name": name,
                    "field": field,
                    "label": str(item.get("label") or name),
                    "aggregation": aggregation,
                    **({"format": str(item["format"])} if item.get("format") else {}),
                    **({"filter": item["filter"]} if item.get("filter") else {}),
                }
            )
        if len(metrics) > 50:
            raise ReportingError("Un dataset est limite a 50 mesures.")

        computed_fields = []
        computed_names = set()
        for item in data.get("computed_fields") or []:
            name = self._identifier(item.get("name"), "Champ calcule")
            if name in computed_names:
                raise ReportingError(f"Champ calcule duplique: {name}")
            computed_names.add(name)
            formula = str(item.get("formula") or "").strip()
            stage = str(item.get("stage") or "post").lower()
            if not formula or len(formula) > 500 or stage not in {"post", "query"}:
                raise ReportingError(f"Formule invalide pour {name}.")
            computed_fields.append(
                {
                    "name": name,
                    "label": str(item.get("label") or name),
                    "formula": formula,
                    "stage": stage,
                }
            )

        record_fields = [str(value) for value in data.get("record_fields") or []]
        quick_fields = [str(value) for value in data.get("quick_fields") or []]
        for field in set(record_fields + quick_fields):
            self._path_info(app_label, model_name, field)
        ordering = [str(value) for value in data.get("ordering") or []]
        allowed_ordering = (
            names
            | metric_names
            | {item["field"] for item in dimensions}
            | set(record_fields)
        )
        if any(item.lstrip("-") not in allowed_ordering for item in ordering):
            raise ReportingError("Le tri utilise un champ non declare.")

        allowed_roles = self._roles(data.get("allowed_roles"))
        has_scope = callable(getattr(model, "filter_reporting_queryset", None))
        if not has_scope:
            allowed_roles = sorted(
                self._author_roles() & reporting_user_roles(self.user)
            )
        dataset = existing or ReportingDataset(
            code=self._unique_code(
                ReportingDataset,
                "custom_ds_",
                data.get("title") or "dataset",
                data.get("code") or "",
            ),
            origin=ReportingDataset.Origin.STUDIO,
            created_by=self.user,
        )
        dataset.title = str(data.get("title") or "").strip()
        dataset.description = str(data.get("description") or "")
        dataset.source_kind = ReportingDataset.SourceKind.MODEL
        dataset.source_app_label = app_label
        dataset.source_model = model_name.lower()
        dataset.dimensions = dimensions
        dataset.metrics = metrics
        dataset.computed_fields = computed_fields
        dataset.default_filters = [
            self._filter(item, app_label, model_name)
            for item in data.get("default_filters") or []
        ]
        dataset.ordering = ordering
        dataset.preview_limit = min(max(int(data.get("preview_limit") or 50), 1), 200)
        dataset.allowed_roles = allowed_roles
        dataset.updated_by = self.user
        dataset.metadata = {
            "allow_ad_hoc": False,
            "record_fields": record_fields,
            "quick_fields": quick_fields,
            "max_limit": 5000,
            "cache_ttl_seconds": 0,
            "reporting_scope": "model" if has_scope else "author_only",
        }
        dataset.full_clean(
            exclude=[
                field
                for field in (
                    "default_filters",
                    "metrics",
                    "computed_fields",
                    "ordering",
                )
                if not getattr(dataset, field)
            ]
        )
        if existing:
            declared = names | metric_names | computed_names
            for visualization in existing.visualizations.all():
                query = (visualization.config or {}).get("query") or {}
                references = set(query.get("dimensions") or []) | set(
                    query.get("metrics") or []
                )
                if query.get("mode") == "records":
                    references = set(query.get("fields") or []) - set(record_fields)
                else:
                    references -= declared
                if references:
                    raise ReportingError(
                        f"La visualisation {visualization.title} utilise encore: "
                        f"{', '.join(sorted(references))}"
                    )
        return dataset

    def preview_dataset(self, data: dict) -> dict:
        """Validate and execute an unsaved dataset definition."""
        dataset = self.build_dataset(data)
        if dataset.metrics:
            spec = {
                "dimensions": [item["name"] for item in dataset.dimensions[:2]],
                "metrics": [item["name"] for item in dataset.metrics[:2]],
                "limit": 20,
            }
        else:
            spec = {
                "mode": "records",
                "fields": dataset.metadata.get("record_fields")
                or [item["field"] for item in dataset.dimensions[:8]],
                "limit": 20,
            }
        return dataset.run_query(context=self.context, spec=spec)

    @transaction.atomic
    def save_dataset(self, data: dict) -> dict:
        """Preview and persist a validated dataset definition."""
        dataset = self.build_dataset(data)
        self.preview_dataset(data)
        dataset.save()
        return self.dataset_json(dataset)

    def delete_dataset(self, asset_id: Any) -> None:
        """Delete an unused studio dataset, never a catalog dataset."""
        dataset = ReportingDataset.objects.get(pk=asset_id)
        if dataset.origin != ReportingDataset.Origin.STUDIO:
            raise ReportingError("Un dataset catalogue ne peut pas etre supprime.")
        if dataset.visualizations.exists():
            raise ReportingError("Supprimez d'abord les visualisations liees.")
        dataset.delete()

    def build_visualization(self, data: dict) -> ReportingVisualization:
        """Validate input and return an unsaved visualization instance."""
        dataset = ReportingDataset.objects.get(pk=data.get("dataset_id"))
        existing = (
            ReportingVisualization.objects.get(pk=data["id"])
            if data.get("id")
            else None
        )
        kind = str(data.get("kind") or "").lower()
        kind_config = get_visualization_type(kind)
        if not kind_config:
            raise ReportingError(f"Type de visualisation non supporte: {kind}")
        dimension_names = {item.get("name") for item in dataset.dimensions}
        metric_names = {item.get("name") for item in dataset.metrics}
        dimensions = [str(value) for value in data.get("dimensions") or []]
        metrics = [str(value) for value in data.get("metrics") or []]
        if not set(dimensions).issubset(dimension_names) or not set(metrics).issubset(
            metric_names
        ):
            raise ReportingError(
                "La visualisation utilise un champ semantique inconnu."
            )
        mode = str(data.get("query_mode") or "aggregate").lower()
        if kind == "table" and mode == "records":
            fields = [str(value) for value in data.get("fields") or []]
            if not fields or not set(fields).issubset(
                set(dataset.metadata.get("record_fields") or [])
            ):
                raise ReportingError(
                    "Les colonnes detail doivent appartenir aux champs records."
                )
            query = {"mode": "records", "fields": fields}
        else:
            if (
                len(dimensions) < kind_config.required_dimensions
                or len(metrics) < kind_config.required_metrics
            ):
                raise ReportingError(
                    "Dimensions ou mesures insuffisantes pour ce type."
                )
            if (
                kind_config.max_dimensions
                and len(dimensions) > kind_config.max_dimensions
            ):
                raise ReportingError("Trop de dimensions pour ce type.")
            if kind_config.max_metrics and len(metrics) > kind_config.max_metrics:
                raise ReportingError("Trop de mesures pour ce type.")
            query = {"mode": "aggregate", "dimensions": dimensions, "metrics": metrics}
        config = {"query": query}
        for source, target in (
            ("x_axis", "x_axis"),
            ("category", "category"),
            ("value", "value"),
            ("metric", "metric"),
            ("format", "format"),
        ):
            if data.get(source):
                config[target] = data[source]
        if data.get("y_axes"):
            config["y_axis"] = data["y_axes"]
        for key in ("colors", "columns"):
            if data.get(key):
                config[key] = data[key]
        if kind == "kpi" and metrics:
            config.setdefault("metric", metrics[0])
        if kind_config.category == "chart" and dimensions:
            config.setdefault("x_axis", dimensions[0])
            config.setdefault("y_axis", metrics)
        allowed_fields = self._dataset_fields(dataset)
        default_filters = []
        for item in data.get("default_filters") or []:
            field = str(item.get("field") or "")
            lookup = str(item.get("lookup") or "exact").lower()
            if field not in allowed_fields or lookup not in SUPPORTED_LOOKUPS:
                raise ReportingError(f"Filtre de visualisation non autorise: {field}")
            default_filters.append(
                {"field": field, "lookup": lookup, "value": item.get("value")}
            )
        visualization = existing or ReportingVisualization(
            dataset=dataset,
            code=self._unique_code(
                ReportingVisualization,
                "custom_viz_",
                data.get("title") or "visualisation",
                data.get("code") or "",
                dataset=dataset,
            ),
            origin=ReportingVisualization.Origin.STUDIO,
            created_by=self.user,
        )
        visualization.dataset = dataset
        visualization.title = str(data.get("title") or "").strip()
        visualization.description = str(data.get("description") or "")
        visualization.kind = kind
        visualization.config = config
        visualization.default_filters = default_filters
        visualization.options = {"studio_managed": True}
        visualization.updated_by = self.user
        visualization.full_clean(
            exclude=["default_filters"] if not visualization.default_filters else None
        )
        return visualization

    def preview_visualization(self, data: dict) -> dict:
        """Render an unsaved visualization definition."""
        return self.build_visualization(data).render(context=self.context, limit=20)

    @transaction.atomic
    def save_visualization(self, data: dict) -> dict:
        """Render and persist a validated visualization definition."""
        visualization = self.build_visualization(data)
        visualization.render(context=self.context, limit=20)
        visualization.save()
        return self.visualization_json(visualization)

    def delete_visualization(self, asset_id: Any) -> None:
        """Delete an unused studio visualization."""
        visualization = ReportingVisualization.objects.get(pk=asset_id)
        if visualization.origin != ReportingVisualization.Origin.STUDIO:
            raise ReportingError(
                "Une visualisation catalogue ne peut pas etre supprimee."
            )
        if visualization.blocks.exists():
            raise ReportingError(
                "Cette visualisation est encore utilisee par un rapport."
            )
        visualization.delete()

    def _filter_definition(
        self, item: dict, datasets: dict[str, ReportingDataset]
    ) -> dict:
        name = self._identifier(item.get("name"), "Filtre")
        filter_type = str(item.get("type") or "text").lower()
        if filter_type not in {"date", "select", "text", "number", "query"}:
            raise ReportingError(f"Type de filtre non supporte: {filter_type}")
        targets = []
        for target in item.get("targets") or []:
            dataset_code = str(
                target.get("dataset_code", target.get("datasetCode")) or ""
            )
            dataset = datasets.get(dataset_code)
            field = str(target.get("field") or "")
            lookup = str(target.get("lookup") or "exact").lower()
            if (
                not dataset
                or field not in self._dataset_fields(dataset)
                or lookup not in SUPPORTED_LOOKUPS
            ):
                raise ReportingError(
                    f"Cible de filtre non autorisee: {dataset_code}.{field}"
                )
            targets.append(
                {"datasetCode": dataset_code, "field": field, "lookup": lookup}
            )
        if not targets:
            raise ReportingError(f"Le filtre {name} exige au moins une cible.")
        definition = {
            "name": name,
            "label": str(item.get("label") or name),
            "type": filter_type,
            "field": targets[0]["field"],
            "lookup": targets[0]["lookup"],
            "targets": targets,
        }
        if item.get("options"):
            definition["options"] = item["options"]
        if item.get("related_model", item.get("relatedModel")):
            definition["relatedModel"] = item.get(
                "related_model", item.get("relatedModel")
            )
            definition["graphql"] = {
                "listFieldName": item.get(
                    "list_field_name", item.get("listFieldName", "")
                ),
                "labelField": item.get("label_field", item.get("labelField", "desc")),
            }
        return definition

    def build_report(self, data: dict) -> tuple[ReportingReport, list[dict]]:
        """Validate report blocks, audience, and filter mappings."""
        existing = (
            ReportingReport.objects.get(pk=data["id"]) if data.get("id") else None
        )
        raw_blocks = data.get("blocks") or []
        if not raw_blocks or len(raw_blocks) > 50:
            raise ReportingError("Un rapport doit contenir entre 1 et 50 blocs.")
        ids = [
            str(item.get("visualization_id", item.get("visualizationId")))
            for item in raw_blocks
        ]
        if len(ids) != len(set(ids)):
            raise ReportingError("Une visualisation ne peut apparaitre qu'une fois.")
        visualizations = {
            str(item.pk): item
            for item in ReportingVisualization.objects.select_related("dataset").filter(
                pk__in=ids
            )
        }
        if set(ids) != set(visualizations):
            raise ReportingError("Une visualisation selectionnee est introuvable.")
        blocks, datasets = [], {}
        for position, item in enumerate(raw_blocks, start=1):
            visualization = visualizations[
                str(item.get("visualization_id", item.get("visualizationId")))
            ]
            width = int(item.get("width") or 12)
            if width not in SUPPORTED_WIDTHS:
                raise ReportingError(f"Largeur de bloc non supportee: {width}")
            datasets[visualization.dataset.code] = visualization.dataset
            blocks.append(
                {
                    "visualization": visualization,
                    "position": position,
                    "layout": {"w": width},
                    "title_override": str(
                        item.get("title_override", item.get("titleOverride", "")) or ""
                    ),
                }
            )
        audience = self._roles(data.get("audience_roles", data.get("audienceRoles")))
        for dataset in datasets.values():
            if dataset.allowed_roles and not set(audience).issubset(
                dataset.allowed_roles
            ):
                raise ReportingError(
                    f"Le rapport depasse l'audience de {dataset.title}."
                )
        filters = [
            self._filter_definition(item, datasets)
            for item in data.get("filters") or []
        ]
        if len(filters) > 50:
            raise ReportingError("Un rapport est limite a 50 filtres.")
        report = existing or ReportingReport(
            code=self._unique_code(
                ReportingReport,
                "custom_report_",
                data.get("title") or "rapport",
                data.get("code") or "",
            ),
            origin=ReportingReport.Origin.STUDIO,
            created_by=self.user,
        )
        report.title = str(data.get("title") or "").strip()
        report.description = str(data.get("description") or "")
        report.theme = str(data.get("theme") or "light")
        report.filters = filters
        report.allowed_roles = audience
        report.updated_by = self.user
        report.layout = [
            {
                "visualizationId": str(item["visualization"].pk),
                "position": item["position"],
                **item["layout"],
            }
            for item in blocks
        ]
        report.full_clean(exclude=["filters"] if not report.filters else None)
        return report, blocks

    def preview_report(self, data: dict) -> dict:
        """Render an unsaved report definition."""
        report, blocks = self.build_report(data)
        rendered = []
        for index, item in enumerate(blocks, start=1):
            payload = item["visualization"].render(context=self.context, limit=20)
            if item["title_override"]:
                payload["visualization"]["title"] = item["title_override"]
            rendered.append(
                {
                    "block_id": f"preview-{index}",
                    "visualization": payload["visualization"],
                    "dataset": payload["dataset"],
                    "layout": item["layout"],
                }
            )
        return {
            "report": {
                "code": report.code,
                "title": report.title,
                "description": report.description,
                "theme": report.theme,
                "layout": report.layout,
            },
            "visualizations": rendered,
            "filters": report.filters,
            "export_formats": [],
        }

    @transaction.atomic
    def save_report(self, data: dict) -> dict:
        """Render and atomically persist a report and its blocks."""
        report, blocks = self.build_report(data)
        self.preview_report(data)
        report.save()
        report.blocks.all().delete()
        ReportingReportBlock.objects.bulk_create(
            [ReportingReportBlock(report=report, **item) for item in blocks]
        )
        return self.report_json(report)

    def delete_report(self, asset_id: Any) -> None:
        """Delete a studio report, never a catalog report."""
        report = ReportingReport.objects.get(pk=asset_id)
        if report.origin != ReportingReport.Origin.STUDIO:
            raise ReportingError("Un rapport catalogue ne peut pas etre supprime.")
        report.delete()

    def capabilities(self) -> dict:
        """Describe models, roles, and reporting features available to the author."""
        roles = []
        for name in Group.objects.order_by("name").values_list("name", flat=True):
            definition = role_manager.get_role_definition(name)
            roles.append(
                {
                    "name": name,
                    "description": (
                        getattr(definition, "description", "") if definition else ""
                    ),
                }
            )
        return {
            "models": list_available_models_for_user(self.user),
            "roles": roles,
            "visualizationKinds": sorted(item.name for item in get_available_types()),
            "aggregations": sorted(SUPPORTED_AGGREGATIONS),
            "transforms": sorted(SUPPORTED_TRANSFORMS - {""}),
            "computedFieldStages": ["post", "query"],
            "computedFieldFunctions": {
                "post": sorted(name for name in SAFE_BUILTINS if name.upper() == name),
                "query": sorted(SAFE_QUERY_BUILTINS),
            },
            "computedFieldOperators": ["+", "-", "*", "/", "%", "**"],
            "widths": sorted(SUPPORTED_WIDTHS),
            "limits": {"dimensions": 50, "metrics": 50, "filters": 50, "blocks": 50},
        }

    def list_datasets(self) -> list[dict]:
        """Serialize all datasets available in the authoring catalog."""
        return [
            self.dataset_json(item)
            for item in ReportingDataset.objects.prefetch_related("visualizations")
        ]

    def list_visualizations(self) -> list[dict]:
        """Serialize all visualizations available in the authoring catalog."""
        return [
            self.visualization_json(item)
            for item in ReportingVisualization.objects.select_related("dataset")
        ]

    def list_reports(self) -> list[dict]:
        """Serialize all reports available in the authoring catalog."""
        return [
            self.report_json(item)
            for item in ReportingReport.objects.prefetch_related(
                "blocks__visualization__dataset"
            )
        ]

    def dataset_json(self, dataset: ReportingDataset) -> dict:
        """Serialize one dataset for the studio client."""
        return {
            "id": str(dataset.pk),
            "code": dataset.code,
            "title": dataset.title,
            "description": dataset.description,
            "sourceAppLabel": dataset.source_app_label,
            "sourceModel": dataset.source_model,
            "dimensions": dataset.dimensions,
            "metrics": dataset.metrics,
            "computedFields": dataset.computed_fields,
            "defaultFilters": dataset.default_filters,
            "ordering": dataset.ordering,
            "previewLimit": dataset.preview_limit,
            "allowedRoles": dataset.allowed_roles,
            "metadata": {
                **(dataset.metadata or {}),
                "record_fields": self._dataset_record_fields(dataset),
            },
            "managed": dataset.origin == ReportingDataset.Origin.STUDIO,
        }

    @staticmethod
    def visualization_json(visualization: ReportingVisualization) -> dict:
        """Serialize one visualization for the studio client."""
        return {
            "id": str(visualization.pk),
            "code": visualization.code,
            "title": visualization.title,
            "description": visualization.description,
            "datasetId": str(visualization.dataset_id),
            "datasetCode": visualization.dataset.code,
            "datasetTitle": visualization.dataset.title,
            "kind": visualization.kind,
            "config": visualization.config,
            "defaultFilters": visualization.default_filters,
            "managed": visualization.origin == ReportingVisualization.Origin.STUDIO,
        }

    @staticmethod
    def report_json(report: ReportingReport) -> dict:
        """Serialize one report and its blocks for the studio client."""
        return {
            "id": str(report.pk),
            "code": report.code,
            "title": report.title,
            "description": report.description,
            "theme": report.theme,
            "filters": report.filters,
            "layout": report.layout,
            "audienceRoles": report.allowed_roles,
            "managed": report.origin == ReportingReport.Origin.STUDIO,
            "blocks": [
                {
                    "visualizationId": str(block.visualization_id),
                    "visualizationTitle": block.visualization.title,
                    "datasetCode": block.visualization.dataset.code,
                    "position": block.position,
                    "width": (block.layout or {}).get("w", 12),
                    "titleOverride": block.title_override,
                }
                for block in report.blocks.all()
            ],
        }


__all__ = ["ReportingStudioService"]
