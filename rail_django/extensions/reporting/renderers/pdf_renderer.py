"""
PDF export renderer.

Requires ``weasyprint`` as an optional dependency. This renderer is only
registered if weasyprint is installed (``pip install rail-django[pdf]``).

Attributes:
    PdfRenderer: Renderer producing PDF output from HTML tables.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import ExportRenderer

try:
    import weasyprint

    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False


class PdfRenderer(ExportRenderer):
    """
    Renderer PDF pour les exports de données reporting.

    Génère un document PDF à partir d'un template HTML tabulaire.
    Supporte le titre, la description, et un style professionnel par défaut.

    Nécessite ``weasyprint``. Non disponible si le package n'est pas installé.

    Options disponibles:
        - ``title`` (str): Titre du document PDF.
        - ``description`` (str): Description sous le titre.
        - ``orientation`` (str): ``portrait`` ou ``landscape`` (défaut: ``landscape``).
        - ``columns`` (list[str]): Colonnes à inclure.
        - ``page_size`` (str): Taille de page CSS (défaut: ``A4``).

    Raises:
        ImportError: Si ``weasyprint`` n'est pas installé.
    """

    format_name = "pdf"
    content_type = "application/pdf"
    file_extension = "pdf"

    def __init__(self) -> None:
        if not HAS_WEASYPRINT:
            raise ImportError(
                "Le renderer PDF necessite 'weasyprint'. "
                "Installez-le avec: pip install weasyprint"
            )

    def render(
        self,
        payload: dict[str, Any],
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> bytes:
        """
        Transforme un payload reporting en document PDF.

        Args:
            payload: Dictionnaire contenant ``rows`` et ``columns``.
            options: Options PDF (title, description, orientation, columns).

        Returns:
            Contenu PDF en bytes.
        """
        options = options or {}
        title = str(options.get("title", "Export BI"))
        description = str(options.get("description", ""))
        orientation = str(options.get("orientation", "landscape"))
        page_size = str(options.get("page_size", "A4"))

        rows = payload.get("rows") or []

        # Determine columns
        column_names = options.get("columns")
        if not column_names:
            columns_meta = payload.get("columns") or []
            if columns_meta:
                column_names = [col.get("name", "") for col in columns_meta if col.get("name")]
            else:
                column_names = list(rows[0].keys()) if rows else []

        columns_meta = payload.get("columns") or []
        label_map = {
            col.get("name", ""): col.get("label", col.get("name", ""))
            for col in columns_meta
        }

        html = self._build_html(
            title=title,
            description=description,
            column_names=column_names,
            label_map=label_map,
            rows=rows,
            orientation=orientation,
            page_size=page_size,
        )

        doc = weasyprint.HTML(string=html)
        return doc.write_pdf()

    @staticmethod
    def _build_html(
        *,
        title: str,
        description: str,
        column_names: list[str],
        label_map: dict[str, str],
        rows: list[dict[str, Any]],
        orientation: str,
        page_size: str,
    ) -> str:
        """
        Construit le template HTML pour le rendu PDF.

        Args:
            title: Titre du document.
            description: Description sous le titre.
            column_names: Noms des colonnes à afficher.
            label_map: Mapping nom → label pour les en-têtes.
            rows: Données à afficher.
            orientation: Orientation de la page.
            page_size: Taille de page CSS.

        Returns:
            Chaîne HTML complète.
        """
        import html as html_module

        header_cells = "".join(
            f"<th>{html_module.escape(label_map.get(name, name))}</th>"
            for name in column_names
        )
        body_rows = []
        for row in rows:
            cells = "".join(
                f"<td>{html_module.escape(str(row.get(name, '')))}</td>"
                for name in column_names
            )
            body_rows.append(f"<tr>{cells}</tr>")

        desc_html = f"<p class='description'>{html_module.escape(description)}</p>" if description else ""

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html_module.escape(title)}</title>
<style>
@page {{
    size: {page_size} {orientation};
    margin: 1.5cm;
}}
body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
    color: #333;
}}
h1 {{
    font-size: 16pt;
    color: #2B579A;
    margin-bottom: 4px;
}}
.description {{
    color: #666;
    font-size: 9pt;
    margin-bottom: 12px;
}}
.meta {{
    font-size: 8pt;
    color: #999;
    margin-bottom: 16px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    page-break-inside: auto;
}}
tr {{
    page-break-inside: avoid;
}}
th {{
    background-color: #2B579A;
    color: white;
    font-weight: bold;
    padding: 6px 8px;
    text-align: left;
    font-size: 9pt;
}}
td {{
    padding: 5px 8px;
    border-bottom: 1px solid #e0e0e0;
    font-size: 9pt;
}}
tr:nth-child(even) td {{
    background-color: #f7f9fc;
}}
</style>
</head>
<body>
<h1>{html_module.escape(title)}</h1>
{desc_html}
<p class="meta">{len(rows)} ligne(s)</p>
<table>
<thead><tr>{header_cells}</tr></thead>
<tbody>{"".join(body_rows)}</tbody>
</table>
</body>
</html>"""


__all__ = ["PdfRenderer"]
