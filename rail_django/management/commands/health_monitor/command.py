"""
Django management command for health monitoring.
"""

import json
from typing import Any, Optional

from django.core.management.base import BaseCommand, CommandError

from .monitor import HealthMonitor
from ....extensions.health import health_checker


class Command(BaseCommand):
    """Django management command for health monitoring."""

    help = "Monitor GraphQL system health with continuous checks and alerting"

    def add_arguments(self, parser):
        parser.add_argument(
            "--duration",
            type=int,
            help="Monitoring duration in minutes (default: run indefinitely)",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Check interval in seconds (default: 60)",
        )
        parser.add_argument(
            "--config-file",
            type=str,
            help="Path to JSON configuration file",
        )
        parser.add_argument(
            "--enable-alerts",
            action="store_true",
            help="Enable email alerts (requires email configuration)",
        )
        parser.add_argument(
            "--alert-recipients",
            type=str,
            nargs="+",
            help="Email addresses for alerts",
        )
        parser.add_argument(
            "--summary-only",
            action="store_true",
            help="Show health summary and exit",
        )

    def handle(self, *args, **options):
        """Handle the management command."""
        try:
            # Load configuration
            config = self._load_config(options)

            # Create monitor
            monitor = HealthMonitor(config)

            if options["summary_only"]:
                # Just show a quick health check
                health_report = health_checker.get_comprehensive_health_report()
                self._display_health_report(health_report)
                return

            # Start monitoring
            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting health monitoring (interval: {config['check_interval_seconds']}s)"
                )
            )

            if options["duration"]:
                self.stdout.write(f"Monitoring for {options['duration']} minutes...")
            else:
                self.stdout.write("Monitoring indefinitely (Ctrl+C to stop)...")

            monitor.start_monitoring(options["duration"])

            # Show summary
            summary = monitor.get_health_summary()
            self._display_summary(summary)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nMonitoring stopped by user"))
        except Exception as e:
            raise CommandError(f"Health monitoring failed: {e}")

    def _load_config(self, options: dict[str, Any]) -> dict[str, Any]:
        """Load monitoring configuration."""
        config = HealthMonitor()._get_default_config()

        # Override with command line options
        if options["interval"]:
            config["check_interval_seconds"] = options["interval"]

        if options["enable_alerts"]:
            config["enable_email_alerts"] = True

        if options["alert_recipients"]:
            config["email_recipients"] = options["alert_recipients"]

        # Load from config file if provided
        if options["config_file"]:
            try:
                with open(options["config_file"], "r") as f:
                    file_config = json.load(f)
                    config.update(file_config)
            except Exception as e:
                raise CommandError(f"Failed to load config file: {e}")

        return config

    def _display_health_report(self, health_report: dict[str, Any]):
        """Display health report in a formatted way."""
        status = health_report["overall_status"]

        # Status with color
        if status == "healthy":
            status_display = self.style.SUCCESS(status.upper())
        elif status == "degraded":
            status_display = self.style.WARNING(status.upper())
        else:
            status_display = self.style.ERROR(status.upper())

        self.stdout.write(f"\nSystem Health Status: {status_display}")
        self.stdout.write(f"Timestamp: {health_report['timestamp']}")

        # Summary
        summary = health_report["summary"]
        self.stdout.write(f"\nComponent Summary:")
        self.stdout.write(f"  Healthy: {summary['healthy']}")
        self.stdout.write(f"  Degraded: {summary['degraded']}")
        self.stdout.write(f"  Unhealthy: {summary['unhealthy']}")

        # System metrics
        if "system_metrics" in health_report:
            metrics = health_report["system_metrics"]
            self.stdout.write(f"\nSystem Metrics:")
            self.stdout.write(
                f"  CPU Usage: {metrics.get('cpu_usage_percent', 0):.1f}%"
            )
            self.stdout.write(
                f"  Memory Usage: {metrics.get('memory_usage_percent', 0):.1f}%"
            )
            self.stdout.write(
                f"  Disk Usage: {metrics.get('disk_usage_percent', 0):.1f}%"
            )
            self.stdout.write(
                f"  Cache Hit Rate: {metrics.get('cache_hit_rate', 0):.1f}%"
            )

        # Recommendations
        if health_report.get("recommendations"):
            self.stdout.write(f"\nRecommendations:")
            for rec in health_report["recommendations"]:
                self.stdout.write(f"  • {rec}")

    def _display_summary(self, summary: dict[str, Any]):
        """Display monitoring summary."""
        self.stdout.write(self.style.SUCCESS("\n=== Monitoring Summary ==="))
        self.stdout.write(
            f"Duration: {summary['monitoring_duration_minutes']:.1f} minutes"
        )
        self.stdout.write(f"Total Checks: {summary['total_checks']}")
        self.stdout.write(
            f"Average Healthy Components: {summary['average_healthy_components']:.1f}"
        )
        self.stdout.write(f"Average CPU Usage: {summary['average_cpu_usage']:.1f}%")
        self.stdout.write(
            f"Average Memory Usage: {summary['average_memory_usage']:.1f}%"
        )
        self.stdout.write(f"Total Alerts: {summary['total_alerts']}")
        self.stdout.write(f"Recent Alerts (1h): {summary['recent_alerts']}")
