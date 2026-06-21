"""
Visualization type registry for the BI reporting module.

Provides a pluggable system for registering custom visualization types
beyond the built-in ones. Each type defines its requirements (dimensions,
metrics), default configuration, and display metadata.

Usage::

    from rail_django.extensions.reporting.visualization_registry import (
        register_visualization_type,
        VisualizationTypeConfig,
    )

    register_visualization_type(VisualizationTypeConfig(
        name="custom_chart",
        label="Graphique personnalise",
        icon="chart-custom",
        required_dimensions=1,
        required_metrics=1,
    ))

Attributes:
    VisualizationTypeConfig: Configuration dataclass for a visualization type.
    register_visualization_type: Register a custom type in the global registry.
    get_visualization_type: Retrieve a type configuration by name.
    get_available_types: List all registered types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VisualizationTypeConfig:
    """
    Configuration pour un type de visualisation.

    Attributes:
        name: Identifiant unique du type (ex: ``bar``, ``scatter``).
        label: Libellé affiché en français.
        icon: Nom d'icône pour le frontend (ex: ``chart-bar``).
        description: Description du type de visualisation.
        default_config: Configuration par défaut pour les nouvelles instances.
        required_dimensions: Nombre minimum de dimensions requises.
        max_dimensions: Nombre maximum de dimensions supportées (``0`` = illimité).
        required_metrics: Nombre minimum de métriques requises.
        max_metrics: Nombre maximum de métriques supportées (``0`` = illimité).
        supports_pivot: Indique si le type supporte les données pivotées.
        category: Catégorie de regroupement (ex: ``chart``, ``table``, ``indicator``).
    """

    name: str
    label: str
    icon: str = ""
    description: str = ""
    default_config: dict[str, Any] = field(default_factory=dict)
    required_dimensions: int = 0
    max_dimensions: int = 0
    required_metrics: int = 0
    max_metrics: int = 0
    supports_pivot: bool = False
    category: str = "chart"


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_VISUALIZATION_REGISTRY: dict[str, VisualizationTypeConfig] = {}


def register_visualization_type(config: VisualizationTypeConfig) -> None:
    """
    Enregistre un type de visualisation dans le registre global.

    Args:
        config: Configuration du type à enregistrer.

    Raises:
        ValueError: Si ``name`` est vide.
    """
    if not config.name:
        raise ValueError("Le type de visualisation doit avoir un 'name'.")
    _VISUALIZATION_REGISTRY[config.name] = config


def get_visualization_type(name: str) -> Optional[VisualizationTypeConfig]:
    """
    Récupère la configuration d'un type de visualisation.

    Args:
        name: Identifiant du type.

    Returns:
        Configuration ou ``None`` si non trouvée.
    """
    return _VISUALIZATION_REGISTRY.get(name)


def get_available_types() -> list[VisualizationTypeConfig]:
    """
    Liste tous les types de visualisation enregistrés.

    Returns:
        Liste triée par catégorie puis par nom.
    """
    return sorted(
        _VISUALIZATION_REGISTRY.values(),
        key=lambda c: (c.category, c.name),
    )


def get_type_choices() -> list[tuple[str, str]]:
    """
    Retourne les choix pour un champ Django ``CharField(choices=...)``.

    Returns:
        Liste de tuples ``(name, label)`` compatible avec Django.
    """
    return [(t.name, t.label) for t in get_available_types()]


# ---------------------------------------------------------------------------
# Built-in visualization types
# ---------------------------------------------------------------------------

_BUILTIN_TYPES = [
    VisualizationTypeConfig(
        name="table",
        label="Tableau",
        icon="table",
        description="Tableau de donnees avec colonnes triables.",
        category="table",
        required_dimensions=0,
        required_metrics=0,
    ),
    VisualizationTypeConfig(
        name="bar",
        label="Histogramme",
        icon="chart-bar",
        description="Graphique en barres verticales.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="line",
        label="Courbe",
        icon="chart-line",
        description="Graphique en courbes pour les tendances temporelles.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="pie",
        label="Camembert",
        icon="chart-pie",
        description="Graphique circulaire pour les proportions.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
        max_dimensions=1,
    ),
    VisualizationTypeConfig(
        name="kpi",
        label="Indicateur",
        icon="gauge",
        description="Indicateur cle de performance (KPI) avec valeur unique.",
        category="indicator",
        required_dimensions=0,
        required_metrics=1,
        max_metrics=3,
    ),
    VisualizationTypeConfig(
        name="area",
        label="Aire",
        icon="chart-area",
        description="Graphique en aires empilees.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="pivot",
        label="Pivot",
        icon="table-pivot",
        description="Tableau croise dynamique.",
        category="table",
        required_dimensions=2,
        required_metrics=1,
        supports_pivot=True,
    ),
    VisualizationTypeConfig(
        name="heatmap",
        label="Heatmap",
        icon="grid-heat",
        description="Carte de chaleur pour les correlations.",
        category="chart",
        required_dimensions=2,
        required_metrics=1,
    ),
    # New types for variety
    VisualizationTypeConfig(
        name="scatter",
        label="Nuage de points",
        icon="chart-scatter",
        description="Nuage de points pour la correlation entre 2 metriques.",
        category="chart",
        required_dimensions=1,
        required_metrics=2,
        max_metrics=3,
    ),
    VisualizationTypeConfig(
        name="funnel",
        label="Entonnoir",
        icon="filter",
        description="Graphique en entonnoir pour les processus sequentiels.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
        max_dimensions=1,
    ),
    VisualizationTypeConfig(
        name="gauge",
        label="Jauge",
        icon="speedometer",
        description="Indicateur circulaire avec seuils de reference.",
        category="indicator",
        required_dimensions=0,
        required_metrics=1,
        max_metrics=1,
        default_config={
            "thresholds": [
                {"value": 0.33, "color": "#e74c3c"},
                {"value": 0.66, "color": "#f39c12"},
                {"value": 1.0, "color": "#27ae60"},
            ]
        },
    ),
    VisualizationTypeConfig(
        name="treemap",
        label="Carte proportionnelle",
        icon="grid-tree",
        description="Visualisation hierarchique des proportions.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="map",
        label="Carte geographique",
        icon="map",
        description="Carte geographique avec code pays ou lat/lng.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
        default_config={"geo_field_type": "country_code"},
    ),
    VisualizationTypeConfig(
        name="sankey",
        label="Diagramme de flux",
        icon="flow",
        description="Diagramme de Sankey pour les flux entre categories.",
        category="chart",
        required_dimensions=2,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="waterfall",
        label="Cascade",
        icon="chart-waterfall",
        description="Graphique en cascade montrant les contributions +/-.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="donut",
        label="Anneau",
        icon="chart-donut",
        description="Graphique en anneau (variante du camembert).",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
        max_dimensions=1,
    ),
    VisualizationTypeConfig(
        name="radar",
        label="Radar",
        icon="chart-radar",
        description="Graphique radar pour comparer plusieurs metriques.",
        category="chart",
        required_dimensions=1,
        required_metrics=1,
    ),
    VisualizationTypeConfig(
        name="pdf",
        label="Export PDF",
        icon="file-pdf",
        description="Export PDF pour impression.",
        category="export",
        required_dimensions=0,
        required_metrics=0,
    ),
]

# Auto-register all built-in types
for _builtin in _BUILTIN_TYPES:
    register_visualization_type(_builtin)


__all__ = [
    "VisualizationTypeConfig",
    "register_visualization_type",
    "get_visualization_type",
    "get_available_types",
    "get_type_choices",
]
