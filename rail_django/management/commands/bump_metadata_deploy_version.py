from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError

from rail_django.extensions.metadata.deploy_version import bump_deploy_version


class Command(BaseCommand):
    help = "Bump the deployment-level metadata version."

    def add_arguments(self, parser):
        parser.add_argument(
            "--key",
            default=None,
            help="Metadata deploy version key (default: settings key or 'default').",
        )
        parser.add_argument(
            "--value",
            default=None,
            help="Explicit version value (defaults to random UUID).",
        )

    def handle(self, *args, **options):
        try:
            version = bump_deploy_version(
                key=options.get("key"), value=options.get("value")
            )
            self.stdout.write(
                self.style.SUCCESS(f"Metadata deploy version: {version}")
            )
        except (OperationalError, ProgrammingError) as exc:
            self.stderr.write(
                self.style.WARNING(
                    f"Unable to bump metadata deploy version (DB not ready): {exc}"
                )
            )
