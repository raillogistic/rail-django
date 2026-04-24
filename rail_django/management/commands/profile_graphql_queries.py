"""Profile captured GraphQL query samples for N+1 risk signals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from rail_django.debugging.query_analyzer import (
    ProductionQueryProfiler,
    QueryAnalyzer,
    QueryProfileInput,
)


class Command(BaseCommand):
    """Analyze production GraphQL query samples with QueryAnalyzer."""

    help = "Profile GraphQL query samples for complexity and N+1 risk patterns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--query",
            action="append",
            default=[],
            help="GraphQL query text to analyze. Can be passed multiple times.",
        )
        parser.add_argument(
            "--query-file",
            action="append",
            default=[],
            help="Path to a .graphql, .json, or .jsonl file of captured queries.",
        )
        parser.add_argument(
            "--schema-file",
            default=None,
            help="Optional GraphQL SDL schema file used for validation.",
        )
        parser.add_argument(
            "--max-complexity",
            type=int,
            default=1000,
            help="Maximum query complexity used by the analyzer.",
        )
        parser.add_argument(
            "--max-depth",
            type=int,
            default=15,
            help="Maximum query depth used by the analyzer.",
        )
        parser.add_argument(
            "--expensive-field",
            action="append",
            default=[],
            help="Field name or path to treat as expensive. Can be repeated.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format.",
        )
        parser.add_argument(
            "--fail-on-risk",
            action="store_true",
            help="Exit with an error when any N+1 risk signal is found.",
        )

    def handle(self, *args, **options):
        samples = self._load_samples(options["query"], options["query_file"])
        if not samples:
            raise CommandError("Provide at least one --query or --query-file value.")

        schema_string = self._read_optional_file(options["schema_file"])
        expensive_fields = {str(field) for field in options["expensive_field"] if field}
        field_complexity_map = {field: 11 for field in expensive_fields}

        analyzer = QueryAnalyzer(
            schema_string=schema_string,
            max_complexity=options["max_complexity"],
            max_depth=options["max_depth"],
            field_complexity_map=field_complexity_map,
            expensive_fields=expensive_fields,
        )
        report = ProductionQueryProfiler(analyzer).profile(samples)

        if options["format"] == "json":
            self.stdout.write(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        else:
            self._write_text_report(report)

        if options["fail_on_risk"] and report.n_plus_one_risk_count:
            raise CommandError(
                f"Detected {report.n_plus_one_risk_count} query sample(s) with N+1 risk signals."
            )

    def _load_samples(
        self,
        query_values: list[str],
        query_files: list[str],
    ) -> list[QueryProfileInput | dict[str, Any] | str]:
        samples: list[QueryProfileInput | dict[str, Any] | str] = []
        samples.extend(query_values or [])

        for query_file in query_files or []:
            path = Path(query_file)
            if not path.exists():
                raise CommandError(f"Query file does not exist: {path}")
            samples.extend(self._load_query_file(path))

        return samples

    def _load_query_file(
        self, path: Path
    ) -> list[QueryProfileInput | dict[str, Any] | str]:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []

        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            samples: list[dict[str, Any]] = []
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CommandError(
                        f"Invalid JSONL at {path}:{line_number}: {exc}"
                    ) from exc
                if not isinstance(value, dict):
                    raise CommandError(
                        f"JSONL entries must be objects at {path}:{line_number}."
                    )
                samples.append(value)
            return samples

        if suffix == ".json":
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise CommandError(f"Invalid JSON file {path}: {exc}") from exc
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                queries = value.get("queries")
                if isinstance(queries, list):
                    return queries
                return [value]
            raise CommandError("JSON query files must contain an object or a list.")

        return [QueryProfileInput(query=text, source=str(path))]

    def _read_optional_file(self, file_path: str | None) -> str | None:
        if not file_path:
            return None
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Schema file does not exist: {path}")
        return path.read_text(encoding="utf-8")

    def _write_text_report(self, report) -> None:
        self.stdout.write("GraphQL query profile")
        self.stdout.write(f"Analyzed query samples: {report.total_queries}")
        self.stdout.write(f"Observed executions: {report.total_observations}")
        self.stdout.write(f"N+1 risk samples: {report.n_plus_one_risk_count}")
        self.stdout.write(f"High-risk samples: {report.high_risk_count}")
        self.stdout.write(
            f"Worst performance score: {report.worst_performance_score:.1f}"
        )

        for index, entry in enumerate(report.entries, start=1):
            label = entry.operation_name or entry.source or f"query-{index}"
            self.stdout.write("")
            self.stdout.write(
                f"{index}. {label}: score={entry.analysis.performance_score:.1f}, "
                f"depth={entry.analysis.complexity.max_depth}, "
                f"complexity={entry.analysis.complexity.total_score}, "
                f"count={entry.count}"
            )
            if not entry.n_plus_one_issues:
                self.stdout.write("   N+1 risk: none")
                continue
            self.stdout.write("   N+1 risk:")
            for issue in entry.n_plus_one_issues:
                self.stdout.write(f"   - [{issue.severity.value}] {issue.message}")
