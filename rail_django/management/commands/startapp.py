import os
from importlib import resources

from django.core.management.commands.startapp import Command as StartAppCommand

class Command(StartAppCommand):
    help = (
        "Creates a Django app directory structure for the given app name "
        "in the current directory or optionally in the given directory."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--minimal",
            action="store_true",
            help="Create a minimal app structure (no admin, apps, views).",
        )

    def handle(self, **options):
        if not options.get("template") and not options.get("minimal"):
            template_path = resources.files("rail_django").joinpath(
                "scaffolding",
                "app_template",
            )
            options["template"] = os.fspath(template_path)
        if options.get("minimal"):
            # If minimal flag is set, force the template to our minimal one
            # unless the user explicitly provided another template (which would be ambiguous, 
            # but let's assume --minimal takes precedence or acts as a shortcut)
            
            # If user provided --template, we might want to warn or error, 
            # but simply overriding it is effective for this specific flag.
            
            template_path = resources.files("rail_django").joinpath(
                "scaffolding",
                "app_template_minimal",
            )
            options["template"] = os.fspath(template_path)

        super().handle(**options)
