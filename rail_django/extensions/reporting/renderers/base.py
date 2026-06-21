"""
Abstract base class and registry for export renderers.

Attributes:
    ExportRenderer: Abstract base class for all renderers.
    RendererRegistry: Global registry mapping format names to renderer instances.
    get_renderer: Lookup a renderer by format name.
    register_renderer: Register a renderer instance in the global registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any, Optional, Union


class ExportRenderer(ABC):
    """
    Interface pour les renderers d'export du reporting.

    Chaque renderer transforme un payload de données reporting en fichier
    binaire dans un format spécifique.

    Attributes:
        format_name: Identifiant du format (ex: ``csv``, ``json``, ``xlsx``).
        content_type: Type MIME du fichier produit.
        file_extension: Extension du fichier (sans le point).
    """

    format_name: str = ""
    content_type: str = "application/octet-stream"
    file_extension: str = "bin"

    @abstractmethod
    def render(
        self,
        payload: dict[str, Any],
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> bytes:
        """
        Transforme un payload reporting en contenu binaire.

        Args:
            payload: Dictionnaire de résultats (``rows``, ``columns``, etc.).
            options: Options spécifiques au renderer (delimiter, encoding, etc.).

        Returns:
            Contenu du fichier en bytes.
        """

    def render_to_stream(
        self,
        payload: dict[str, Any],
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> BytesIO:
        """
        Transforme un payload en stream BytesIO.

        Méthode de commodité qui encapsule ``render()`` dans un BytesIO.

        Args:
            payload: Dictionnaire de résultats.
            options: Options spécifiques au renderer.

        Returns:
            BytesIO contenant le fichier.
        """
        content = self.render(payload, options=options)
        stream = BytesIO(content)
        stream.seek(0)
        return stream

    def get_filename(self, base_name: str = "export") -> str:
        """
        Génère un nom de fichier avec l'extension appropriée.

        Args:
            base_name: Nom de base du fichier (sans extension).

        Returns:
            Nom de fichier complet (ex: ``export.csv``).
        """
        return f"{base_name}.{self.file_extension}"


class RendererRegistry:
    """
    Registre global des renderers d'export disponibles.

    Associe des noms de format (``csv``, ``json``, etc.) à des instances
    de ``ExportRenderer``.
    """

    def __init__(self) -> None:
        self._renderers: dict[str, ExportRenderer] = {}

    def register(self, renderer: ExportRenderer) -> None:
        """
        Enregistre un renderer dans le registre.

        Args:
            renderer: Instance de renderer à enregistrer.

        Raises:
            ValueError: Si ``format_name`` n'est pas défini.
        """
        if not renderer.format_name:
            raise ValueError(
                f"Le renderer {renderer.__class__.__name__} doit definir 'format_name'."
            )
        self._renderers[renderer.format_name.lower()] = renderer

    def get(self, format_name: str) -> Optional[ExportRenderer]:
        """
        Récupère un renderer par nom de format.

        Args:
            format_name: Identifiant du format (ex: ``csv``).

        Returns:
            Instance de renderer ou ``None``.
        """
        return self._renderers.get(format_name.lower())

    def available_formats(self) -> list[str]:
        """
        Liste les formats d'export disponibles.

        Returns:
            Liste triée des noms de format enregistrés.
        """
        return sorted(self._renderers.keys())

    def __contains__(self, format_name: str) -> bool:
        return format_name.lower() in self._renderers


# Global singleton registry
_registry = RendererRegistry()


def register_renderer(renderer: ExportRenderer) -> None:
    """
    Enregistre un renderer dans le registre global.

    Args:
        renderer: Instance de renderer à enregistrer.
    """
    _registry.register(renderer)


def get_renderer(format_name: str) -> ExportRenderer:
    """
    Récupère un renderer depuis le registre global.

    Args:
        format_name: Identifiant du format (ex: ``csv``, ``json``).

    Returns:
        Instance de renderer.

    Raises:
        ValueError: Si le format n'est pas enregistré.
    """
    renderer = _registry.get(format_name)
    if renderer is None:
        available = ", ".join(_registry.available_formats()) or "(aucun)"
        raise ValueError(
            f"Format d'export '{format_name}' non disponible. "
            f"Formats disponibles: {available}"
        )
    return renderer


__all__ = [
    "ExportRenderer",
    "RendererRegistry",
    "get_renderer",
    "register_renderer",
]
