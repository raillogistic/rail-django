"""
HTML documentation generation.
"""

from typing import Optional
from ..schema_introspector import SchemaIntrospection

class HTMLGeneratorMixin:
    """Mixin for generating HTML documentation."""

    def _markdown_to_html(self, markdown_content: str, introspection: Optional[SchemaIntrospection]) -> str:
        """Convert Markdown to HTML (simplified)."""
        html_lines = [
            "<!DOCTYPE html>", "<html lang='en'>", "<head>", "    <meta charset='UTF-8'>",
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"    <title>{introspection.schema_name if introspection else 'GraphQL Schema'} Documentation</title>",
            "    <style>", self._get_default_css(), "    </style>", "</head>", "<body>", "    <div class='container>"
        ]
        lines = markdown_content.split('\n')
        in_code_block = False
        for line in lines:
            if line.startswith('```'):
                if in_code_block: html_lines.append("        </code></pre>"); in_code_block = False
                else: lang = line[3:].strip() or 'text'; html_lines.append(f"        <pre><code class='language-{lang}'>"); in_code_block = True
            elif in_code_block: html_lines.append(f"        {line}")
            elif line.startswith('# '): html_lines.append(f"        <h1>{line[2:]}</h1>")
            elif line.startswith('## '): html_lines.append(f"        <h2>{line[3:]}</h2>")
            elif line.startswith('### '): html_lines.append(f"        <h3>{line[4:]}</h3>")
            elif line.startswith('#### '): html_lines.append(f"        <h4>{line[5:]}</h4>")
            elif line.startswith('- '): html_lines.append(f"        <li>{line[2:]}</li>")
            elif line.startswith('| '):
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                html_lines.append(f"        <tr>{''.join(f'<td>{cell}</td>' for cell in cells)}</tr>")
            elif line.strip(): html_lines.append(f"        <p>{line}</p>")
            else: html_lines.append("")
        html_lines.extend(["    </div>", "</body>", "</html>"])
        return '\n'.join(html_lines)

    def _get_default_css(self) -> str:
        """Get default CSS for HTML."""
        if self.config.custom_css: return self.config.custom_css
        return """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }
        .container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1, h2, h3, h4 { color: #2c3e50; margin-top: 2em; margin-bottom: 1em; }
        h1 { border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        h2 { border-bottom: 2px solid #ecf0f1; padding-bottom: 8px; }
        code { background: #f8f9fa; padding: 2px 6px; border-radius: 3px; font-family: 'Monaco', 'Consolas', monospace; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; border-left: 4px solid #3498db; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; font-weight: 600; }
        ul, ol { padding-left: 30px; }
        li { margin: 5px 0; }
        .deprecated { color: #e74c3c; text-decoration: line-through; }
        """
