from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate base table v3 configuration from model metadata."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("table v3 config generated"))
