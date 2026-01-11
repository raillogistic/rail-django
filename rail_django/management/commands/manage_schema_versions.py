"""Schema versioning management command removed."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Schema versioning has been removed from rail_django."

    def handle(self, *args, **options):
        raise CommandError("Schema versioning has been removed from rail_django.")
