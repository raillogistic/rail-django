import json
from django.core.management.base import BaseCommand, CommandError
from graphene_django.settings import graphene_settings
from graphql import print_schema, get_introspection_query

class Command(BaseCommand):
    help = "Eject the GraphQL schema to SDL (Schema Definition Language) or JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            dest="output_file",
            help="Output file path (default: stdout).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON introspection result instead of SDL.",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="Indentation level for JSON output (default: 2).",
        )

    def handle(self, *args, **options):
        schema = graphene_settings.SCHEMA
        if not schema:
            raise CommandError("GRAPHENE.SCHEMA is not configured or could not be loaded.")

        if options["json"]:
            # get_introspection_query is a function in newer graphql-core versions
            query = get_introspection_query()
            result = schema.execute(query)
            if result.errors:
                raise CommandError(f"Introspection failed: {result.errors}")
            output = json.dumps(result.data, indent=options["indent"])
        else:
            output = print_schema(schema.graphql_schema)

        if options["output_file"]:
            with open(options["output_file"], "w", encoding="utf-8") as f:
                f.write(output)
            self.stdout.write(self.style.SUCCESS(f"Schema written to {options['output_file']}"))
        else:
            self.stdout.write(output)
