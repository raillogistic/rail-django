"""
ReportingVisualizationTemplate model for the BI reporting module.

Provides reusable visualization templates that can be instantiated against
any compatible dataset. Templates define slot-based dimension/metric bindings
and default configurations.

Attributes:
    ReportingVisualizationTemplate: Reusable template model for visualizations.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from django.db import models

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import action_form

from ..security import _reporting_roles, _reporting_operations


class ReportingVisualizationTemplate(models.Model):
    """
    Template réutilisable de visualisation applicable à n'importe quel dataset.

    Un template définit des « slots » pour les dimensions et métriques que
    l'utilisateur lie à des champs concrets lors de l'instanciation.

    Attributes:
        code: Identifiant unique slug du template.
        title: Titre du template.
        description: Description détaillée de l'utilisation du template.
        kind: Type de visualisation (doit correspondre au registre).
        config_template: Configuration avec placeholders ``{{slot_name}}``.
        dimension_slots: Définitions des slots de dimensions.
        metric_slots: Définitions des slots de métriques.
        default_options: Options UI par défaut.
        tags: Tags de catégorisation pour la recherche.
        is_published: Indique si le template est visible.
        created_at: Horodatage de création.
        updated_at: Horodatage de mise à jour.

    Example dimension_slots::

        [
            {"name": "category", "role": "x_axis", "required": true, "label": "Axe X"},
            {"name": "series", "role": "color", "required": false, "label": "Serie"}
        ]

    Example metric_slots::

        [
            {"name": "value", "role": "y_axis", "required": true, "label": "Valeur"},
            {"name": "size", "role": "size", "required": false, "label": "Taille"}
        ]
    """

    code = models.SlugField(
        unique=True,
        max_length=80,
        verbose_name="Code",
    )
    title = models.CharField(
        max_length=120,
        verbose_name="Titre",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description",
    )
    kind = models.CharField(
        max_length=30,
        verbose_name="Type de visualisation",
        help_text="Identifiant du type de visualisation (ex: bar, line, kpi).",
    )
    config_template = models.JSONField(
        default=dict,
        verbose_name="Template de configuration",
        help_text="Configuration avec placeholders {{slot_name}} remplaces lors de l instanciation.",
    )
    dimension_slots = models.JSONField(
        default=list,
        verbose_name="Slots dimensions",
        help_text="Liste de slots: [{name, role, required, label, help_text}].",
    )
    metric_slots = models.JSONField(
        default=list,
        verbose_name="Slots metriques",
        help_text="Liste de slots: [{name, role, required, label, help_text}].",
    )
    default_options = models.JSONField(
        default=dict,
        verbose_name="Options par defaut",
        help_text="Options UI par defaut (theme, animations, couleurs).",
    )
    tags = models.JSONField(
        default=list,
        verbose_name="Tags",
        help_text="Tags pour categoriser et rechercher les templates.",
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name="Publie",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creation",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Mise a jour",
    )

    class Meta:
        app_label = "rail_django"
        verbose_name = "Template de visualisation BI"
        verbose_name_plural = "Templates de visualisation BI"
        ordering = ["kind", "title"]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
            fields={
                "kind": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "is_published": GraphQLMetaBase.FilterField(lookups=["exact"]),
            },
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "title", "code", "kind", "created_at"],
            default=["title"],
        )
        fields = GraphQLMetaBase.Fields(
            read_only=["created_at", "updated_at"],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.kind})"

    def _resolve_config(self, bindings: dict[str, str]) -> dict[str, Any]:
        """
        Resolve placeholders in config_template with actual field bindings.

        Replaces ``{{slot_name}}`` patterns with the bound field values.

        Args:
            bindings: Mapping of slot name to actual field path.

        Returns:
            Resolved configuration dictionary.
        """
        import json
        import re

        config_str = json.dumps(self.config_template or {}, ensure_ascii=False)
        for slot_name, field_value in bindings.items():
            placeholder = "{{" + slot_name + "}}"
            config_str = config_str.replace(placeholder, str(field_value))

        # Warn about unresolved placeholders
        unresolved = re.findall(r"\{\{(\w+)\}\}", config_str)
        if unresolved:
            # Replace unresolved with null
            for name in unresolved:
                config_str = config_str.replace("{{" + name + "}}", "null")

        return json.loads(config_str)

    @action_form(
        title="Instancier le template",
        description="Cree une visualisation concrete a partir du template et des bindings.",
        submit_label="Creer",
        fields={
            "dataset_id": {
                "label": "ID du dataset",
                "type": "number",
                "help_text": "ID du ReportingDataset cible.",
            },
            "bindings": {
                "label": "Bindings",
                "type": "json",
                "help_text": "Mapping slot -> champ du dataset. Ex: {\"category\": \"region\", \"value\": \"revenue\"}.",
            },
            "code": {
                "label": "Code",
                "type": "text",
                "help_text": "Code unique pour la visualisation creee.",
            },
            "title_override": {
                "label": "Titre (optionnel)",
                "type": "text",
            },
        },
    )
    def instantiate(
        self,
        dataset_id: int,
        bindings: Optional[dict] = None,
        code: str = "",
        title_override: str = "",
    ) -> dict:
        """
        Create a ReportingVisualization from this template with bindings.

        Args:
            dataset_id: ID of the target dataset.
            bindings: Mapping of slot names to actual field paths.
            code: Unique code for the new visualization.
            title_override: Optional title override.

        Returns:
            Dictionary with created visualization details.
        """
        from .visualization import ReportingVisualization
        from .dataset import ReportingDataset

        bindings = bindings or {}

        # Validate required slots
        for slot in (self.dimension_slots or []):
            if slot.get("required") and slot.get("name") not in bindings:
                return {
                    "success": False,
                    "error": f"Slot dimension requis manquant: {slot.get('name')}",
                }
        for slot in (self.metric_slots or []):
            if slot.get("required") and slot.get("name") not in bindings:
                return {
                    "success": False,
                    "error": f"Slot metrique requis manquant: {slot.get('name')}",
                }

        # Resolve config
        resolved_config = self._resolve_config(bindings)

        # Build dimensions/metrics from bindings
        query_config = resolved_config.get("query", {})
        if not query_config.get("dimensions"):
            dimensions = []
            for slot in (self.dimension_slots or []):
                field_path = bindings.get(slot.get("name", ""))
                if field_path:
                    dimensions.append({
                        "name": slot.get("name"),
                        "field": field_path,
                        "label": slot.get("label", slot.get("name")),
                    })
            if dimensions:
                query_config["dimensions"] = dimensions

        if not query_config.get("metrics"):
            metrics = []
            for slot in (self.metric_slots or []):
                field_path = bindings.get(slot.get("name", ""))
                if field_path:
                    metrics.append({
                        "name": slot.get("name"),
                        "field": field_path,
                        "aggregation": slot.get("aggregation", "sum"),
                        "label": slot.get("label", slot.get("name")),
                    })
            if metrics:
                query_config["metrics"] = metrics

        resolved_config["query"] = query_config

        viz = ReportingVisualization.objects.create(
            dataset_id=dataset_id,
            code=code or f"{self.code}_{dataset_id}",
            title=title_override or f"{self.title}",
            kind=self.kind,
            config=resolved_config,
            options=copy.deepcopy(self.default_options or {}),
        )

        return {
            "success": True,
            "visualization_id": viz.id,
            "visualization_code": viz.code,
            "template_code": self.code,
        }


__all__ = ["ReportingVisualizationTemplate"]
