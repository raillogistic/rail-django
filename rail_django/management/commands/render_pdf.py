import json
from pathlib import Path

from django.contrib.auth.models import AnonymousUser
from django.core.management.base import BaseCommand, CommandError
from django.http import HttpRequest

from rail_django.extensions.templating import (
    _build_template_context,
    _render_template,
    _sanitize_filename,
    render_pdf,
    render_template_html,
    template_registry,
)


class Command(BaseCommand):
    help = "Render a registered PDF template to a file."

    def add_arguments(self, parser):
        parser.add_argument("template_path", help="Template URL path to render")
        parser.add_argument("--pk", required=True, help="Primary key for model templates")
        parser.add_argument(
            "--output",
            "-o",
            default=None,
            help="Output file path (defaults to <template>-<pk>.pdf)",
        )
        parser.add_argument(
            "--client-data",
            default=None,
            help="Optional JSON string for client data injection",
        )
        parser.add_argument(
            "--html",
            action="store_true",
            help="Render HTML preview instead of PDF",
        )

    def handle(self, *args, **options):
        template_path = options["template_path"]
        pk = options["pk"]
        template_def = template_registry.get(template_path)
        if not template_def:
            raise CommandError(f"Template not found: {template_path}")

        instance = None
        if template_def.model:
            try:
                instance = template_def.model.objects.get(pk=pk)
            except template_def.model.DoesNotExist as exc:
                raise CommandError(f"Instance not found: {pk}") from exc

        client_data = {}
        raw_client_data = options.get("client_data")
        if raw_client_data:
            try:
                client_data = json.loads(raw_client_data)
            except json.JSONDecodeError as exc:
                raise CommandError("Invalid JSON for --client-data") from exc

        request = HttpRequest()
        request.user = AnonymousUser()
        context = _build_template_context(
            request, instance, template_def, client_data, pk=str(pk)
        )

        base_name = f"{template_def.url_path.replace('/', '-')}-{pk}"
        if options["html"]:
            header_html = _render_template(template_def.header_template, context)
            content_html = _render_template(template_def.content_template, context)
            footer_html = _render_template(template_def.footer_template, context)
            output_content = render_template_html(
                header_html=header_html,
                content_html=content_html,
                footer_html=footer_html,
                config=template_def.config,
            )
            default_filename = f"{_sanitize_filename(base_name)}.html"
            mode = "w"
            encoding = "utf-8"
        else:
            output_content = render_pdf(
                template_def.content_template,
                context,
                config=template_def.config,
                header_template=template_def.header_template,
                footer_template=template_def.footer_template,
            )
            default_filename = f"{_sanitize_filename(base_name)}.pdf"
            mode = "wb"
            encoding = None

        output_path = Path(options["output"] or default_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if encoding:
            output_path.write_text(output_content, encoding=encoding)
        else:
            output_path.write_bytes(output_content)

        self.stdout.write(self.style.SUCCESS(f"Rendered: {output_path}"))
