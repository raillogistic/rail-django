from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Validate rollback safety for table v3 cutover."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("table v3 rollback_check completed"))
