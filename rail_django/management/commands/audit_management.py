"""
Management command for audit log operations.
"""

import csv
import json
import logging
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from rail_django.extensions.audit.models import get_audit_event_model
from rail_django.extensions.audit.logger.loggers import audit_logger

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for Security & Compliance Auditing.
    """

    help = "Manage audit logs: export, cleanup, and summary reports."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", required=True)

        # Export subcommand
        export_parser = subparsers.add_parser("export", help="Export audit logs")
        export_parser.add_argument(
            "--format",
            choices=["json", "csv"],
            default="json",
            help="Output format (json or csv)",
        )
        export_parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Export logs from the last N days",
        )
        export_parser.add_argument(
            "--output",
            type=str,
            required=True,
            help="Output file path",
        )

        # Cleanup subcommand
        cleanup_parser = subparsers.add_parser("cleanup", help="Delete old audit logs")
        cleanup_parser.add_argument(
            "--days",
            type=int,
            required=True,
            help="Delete logs older than N days",
        )
        cleanup_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

        # Summary subcommand
        summary_parser = subparsers.add_parser("summary", help="Show security summary")
        summary_parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Show summary for the last N hours",
        )

    def handle(self, *args, **options):
        action = options["action"]

        if action == "export":
            self._handle_export(options)
        elif action == "cleanup":
            self._handle_cleanup(options)
        elif action == "summary":
            self._handle_summary(options)

    def _handle_export(self, options: dict[str, Any]):
        days = options["days"]
        output_format = options["format"]
        output_file = options["output"]

        cutoff = timezone.now() - timedelta(days=days)
        events = get_audit_event_model().objects.filter(timestamp__gte=cutoff)

        self.stdout.write(f"Exporting {events.count()} events since {cutoff}...")

        if output_format == "json":
            self._export_json(events, output_file)
        elif output_format == "csv":
            self._export_csv(events, output_file)

        self.stdout.write(self.style.SUCCESS(f"Exported to {output_file}"))

    def _export_json(self, events, output_file):
        data = []
        for event in events:
            data.append({
                "id": event.id,
                "event_type": event.event_type,
                "severity": event.severity,
                "user_id": event.user_id,
                "username": event.username,
                "client_ip": event.client_ip,
                "timestamp": event.timestamp.isoformat(),
                "additional_data": event.additional_data,
                "success": event.success,
            })
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _export_csv(self, events, output_file):
        if not events.exists():
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("")
            return

        fields = [
            "id", "event_type", "severity", "user_id", "username", 
            "client_ip", "timestamp", "request_path", "success", "error_message"
        ]
        
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            
            for event in events:
                writer.writerow([
                    event.id,
                    event.event_type,
                    event.severity,
                    event.user_id,
                    event.username,
                    event.client_ip,
                    event.timestamp.isoformat(),
                    event.request_path,
                    event.success,
                    event.error_message,
                ])

    def _handle_cleanup(self, options: dict[str, Any]):
        days = options["days"]
        dry_run = options["dry_run"]

        cutoff = timezone.now() - timedelta(days=days)
        qs = get_audit_event_model().objects.filter(timestamp__lt=cutoff)
        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY RUN] Would delete {count} audit events older than {cutoff}.")
            )
        else:
            if count > 0:
                self.stdout.write(f"Deleting {count} audit events older than {cutoff}...")
                qs.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {count} events."))
            else:
                self.stdout.write("No events to delete.")

    def _handle_summary(self, options: dict[str, Any]):
        hours = options["hours"]
        report = audit_logger.get_security_report(hours=hours)

        if "error" in report:
            self.stdout.write(self.style.ERROR(f"Error generating report: {report['error']}"))
            return

        self.stdout.write(self.style.SUCCESS(f"=== Security Summary (Last {hours} hours) ==="))
        self.stdout.write(f"Total Events: {report.get('total_events', 0)}")
        self.stdout.write(f"Successful Logins: {report.get('successful_logins', 0)}")
        
        failed_logins = report.get('failed_logins', 0)
        style = self.style.ERROR if failed_logins > 0 else self.style.SUCCESS
        self.stdout.write(style(f"Failed Logins: {failed_logins}"))
        
        suspicious = report.get('suspicious_activities', 0)
        if suspicious > 0:
            self.stdout.write(self.style.ERROR(f"Suspicious Activities: {suspicious}"))

        top_ips = report.get("top_failed_ips", [])
        if top_ips:
            self.stdout.write("\nTop Failed Login IPs:")
            for item in top_ips:
                self.stdout.write(f"  - {item['client_ip']}: {item['count']}")

        top_users = report.get("top_targeted_users", [])
        if top_users:
            self.stdout.write("\nTop Targeted Users:")
            for item in top_users:
                self.stdout.write(f"  - {item['username']}: {item['count']}")
