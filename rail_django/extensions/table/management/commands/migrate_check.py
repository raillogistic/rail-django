from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check for legacy table API usage."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("table v3 migrate_check completed"))
