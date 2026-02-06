"""
Export form schema JSON for Form API.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from ...extractors.base import FormConfigExtractor


class Command(BaseCommand):
    help = "Export Form API schema as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--app", dest="app", help="App label")
        parser.add_argument("--model", dest="model", help="Model name")
        parser.add_argument("--out", dest="out", help="Output file path")

    def handle(self, *args, **options):
        app = options.get("app")
        model = options.get("model")
        out_path = options.get("out")

        if not app or not model:
            self.stderr.write("Both --app and --model are required.")
            return

        extractor = FormConfigExtractor()
        config = extractor.extract(app, model)
        payload = json.dumps(config, default=str, indent=2)

        if out_path:
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(payload)
            self.stdout.write(self.style.SUCCESS(f"Wrote schema to {out_path}"))
        else:
            self.stdout.write(payload)
