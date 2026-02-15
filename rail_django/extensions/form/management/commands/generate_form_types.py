"""
Generate TypeScript definitions for Form API.
"""

from __future__ import annotations

from typing import Any, List

from django.core.management.base import BaseCommand

from ...extractors.base import FormConfigExtractor
from ...codegen.typescript_generator import generate_typescript_definitions


class Command(BaseCommand):
    help = "Generate TypeScript types for Form API."

    def add_arguments(self, parser):
        parser.add_argument("--app", dest="app", help="App label")
        parser.add_argument("--model", dest="model", help="Model name")
        parser.add_argument("--out", dest="out", help="Output file path")

    def handle(self, *args, **options):
        app = options.get("app")
        model = options.get("model")
        out_path = options.get("out")

        extractor = FormConfigExtractor()
        configs: List[dict[str, Any]] = []

        if app and model:
            configs.append(extractor.extract(app, model))
        else:
            self.stderr.write("Both --app and --model are required.")
            return

        output = generate_typescript_definitions(configs)

        if out_path:
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(output)
            self.stdout.write(self.style.SUCCESS(f"Wrote types to {out_path}"))
        else:
            self.stdout.write(output)
