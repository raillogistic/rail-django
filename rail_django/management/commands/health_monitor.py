"""
Django Management Command for Health Monitoring

This command provides continuous monitoring capabilities for the GraphQL system,
including automated health checks, alerting, and diagnostic reporting.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as django_timezone

from rail_django.extensions.health import HealthStatus, health_checker

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Continuous health monitoring system with alerting capabilities.

    Features:
    - Continuous health monitoring with configurable intervals
    - Alert system for degraded/unhealthy components
    - Historical health data tracking
    - Performance trend analysis
    - Automated recovery suggestions
    """

    def __init__(self, config: dict[str, Any] = None):
        self.config = config or self._get_default_config()
        self.health_history: list[dict[str, Any]] = []
        self.alert_history: list[dict[str, Any]] = []
        self.last_alert_times: dict[str, datetime] = {}

    def _get_default_config(self) -> dict[str, Any]:
        """Get default monitoring configuration."""
        return {
            "check_interval_seconds": 60,  # Check every minute
            "alert_threshold_unhealthy": 1,  # Alert after 1 unhealthy check
            "alert_threshold_degraded": 3,  # Alert after 3 degraded checks
            "alert_cooldown_minutes": 15,  # Don't spam alerts
            "max_history_entries": 1000,  # Keep last 1000 health checks
            "enable_email_alerts": False,
            "email_recipients": [],
            "enable_logging": True,
            "log_level": "INFO",
            "performance_thresholds": {
                "cpu_usage_percent": 80.0,
                "memory_usage_percent": 85.0,
                "disk_usage_percent": 90.0,
                "response_time_ms": 1000.0,
                "cache_hit_rate": 70.0,
            },
        }

    def start_monitoring(self, duration_minutes: Optional[int] = None):
        """
        Start continuous health monitoring.

        Args:
            duration_minutes: How long to monitor (None for indefinite)
        """
        logger.info("Starting health monitoring system...")

        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes else None

        try:
            while True:
                # Perform health check
                health_report = self._perform_health_check()

                # Store in history
                self._store_health_data(health_report)

                # Check for alerts
                self._check_and_send_alerts(health_report)

                # Log status
                if self.config["enable_logging"]:
                    self._log_health_status(health_report)

                # Check if we should stop
                if end_time and time.time() >= end_time:
                    logger.info("Monitoring duration completed")
                    break

                # Wait for next check
                time.sleep(self.config["check_interval_seconds"])

        except KeyboardInterrupt:
            logger.info("Health monitoring stopped by user")
        except Exception as e:
            logger.error(f"Health monitoring error: {e}")
            raise

    def _perform_health_check(self) -> dict[str, Any]:
        """Perform comprehensive health check."""
        try:
            return health_checker.get_comprehensive_health_report()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "overall_status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "summary": {"healthy": 0, "degraded": 0, "unhealthy": 1},
                "components": {},
                "system_metrics": {},
                "recommendations": [f"Health check system error: {str(e)}"],
            }

    def _store_health_data(self, health_report: dict[str, Any]):
        """Store health data in history."""
        self.health_history.append(
            {
                "timestamp": health_report["timestamp"],
                "overall_status": health_report["overall_status"],
                "summary": health_report["summary"],
                "system_metrics": health_report.get("system_metrics", {}),
                "response_times": self._extract_response_times(health_report),
            }
        )

        # Limit history size
        if len(self.health_history) > self.config["max_history_entries"]:
            self.health_history = self.health_history[
                -self.config["max_history_entries"] :
            ]

    def _extract_response_times(
        self, health_report: dict[str, Any]
    ) -> dict[str, float]:
        """Extract response times from health report."""
        response_times = {}

        # Schema response time
        if "schema" in health_report.get("components", {}):
            response_times["schema"] = health_report["components"]["schema"].get(
                "response_time_ms", 0
            )

        # Database response times
        for db_status in health_report.get("components", {}).get("databases", []):
            component = db_status.get("component", "unknown")
            response_times[component] = db_status.get("response_time_ms", 0)

        # Cache response times
        for cache_status in health_report.get("components", {}).get("caches", []):
            component = cache_status.get("component", "unknown")
            response_times[component] = cache_status.get("response_time_ms", 0)

        return response_times

    def _check_and_send_alerts(self, health_report: dict[str, Any]):
        """Check health status and send alerts if necessary."""
        current_time = datetime.now(timezone.utc)

        # Check overall system status
        overall_status = health_report["overall_status"]

        if overall_status == "unhealthy":
            self._send_alert(
                "system_critical",
                {
                    "level": "CRITICAL",
                    "message": "System is in unhealthy state",
                    "details": health_report["summary"],
                    "recommendations": health_report.get("recommendations", []),
                },
            )
        elif overall_status == "degraded":
            self._send_alert(
                "system_degraded",
                {
                    "level": "WARNING",
                    "message": "System performance is degraded",
                    "details": health_report["summary"],
                    "recommendations": health_report.get("recommendations", []),
                },
            )

        # Check individual components
        self._check_component_alerts(health_report)

        # Check performance thresholds
        self._check_performance_alerts(health_report)

    def _check_component_alerts(self, health_report: dict[str, Any]):
        """Check individual component health and send alerts."""
        components = health_report.get("components", {})

        # Check schema
        if "schema" in components:
            schema_status = components["schema"]
            if schema_status["status"] == "unhealthy":
                self._send_alert(
                    "schema_unhealthy",
                    {
                        "level": "CRITICAL",
                        "message": f"GraphQL schema is unhealthy: {schema_status['message']}",
                        "component": "schema",
                    },
                )

        # Check databases
        for db_status in components.get("databases", []):
            if db_status["status"] == "unhealthy":
                self._send_alert(
                    f"database_{db_status['component']}",
                    {
                        "level": "CRITICAL",
                        "message": f"Database {db_status['component']} is unhealthy: {db_status['message']}",
                        "component": db_status["component"],
                    },
                )

        # Check caches
        for cache_status in components.get("caches", []):
            if cache_status["status"] == "unhealthy":
                self._send_alert(
                    f"cache_{cache_status['component']}",
                    {
                        "level": "WARNING",
                        "message": f"Cache {cache_status['component']} is unhealthy: {cache_status['message']}",
                        "component": cache_status["component"],
                    },
                )

    def _check_performance_alerts(self, health_report: dict[str, Any]):
        """Check performance metrics against thresholds."""
        metrics = health_report.get("system_metrics", {})
        thresholds = self.config["performance_thresholds"]

        # CPU usage
        cpu_usage = metrics.get("cpu_usage_percent", 0)
        if cpu_usage > thresholds["cpu_usage_percent"]:
            self._send_alert(
                "high_cpu",
                {
                    "level": "WARNING",
                    "message": f"High CPU usage: {cpu_usage:.1f}%",
                    "metric": "cpu_usage_percent",
                    "value": cpu_usage,
                    "threshold": thresholds["cpu_usage_percent"],
                },
            )

        # Memory usage
        memory_usage = metrics.get("memory_usage_percent", 0)
        if memory_usage > thresholds["memory_usage_percent"]:
            self._send_alert(
                "high_memory",
                {
                    "level": "WARNING",
                    "message": f"High memory usage: {memory_usage:.1f}%",
                    "metric": "memory_usage_percent",
                    "value": memory_usage,
                    "threshold": thresholds["memory_usage_percent"],
                },
            )

        # Disk usage
        disk_usage = metrics.get("disk_usage_percent", 0)
        if disk_usage > thresholds["disk_usage_percent"]:
            self._send_alert(
                "high_disk",
                {
                    "level": "CRITICAL",
                    "message": f"High disk usage: {disk_usage:.1f}%",
                    "metric": "disk_usage_percent",
                    "value": disk_usage,
                    "threshold": thresholds["disk_usage_percent"],
                },
            )

        # Cache hit rate
        cache_hit_rate = metrics.get("cache_hit_rate", 100)
        if cache_hit_rate < thresholds["cache_hit_rate"]:
            self._send_alert(
                "low_cache_hit_rate",
                {
                    "level": "WARNING",
                    "message": f"Low cache hit rate: {cache_hit_rate:.1f}%",
                    "metric": "cache_hit_rate",
                    "value": cache_hit_rate,
                    "threshold": thresholds["cache_hit_rate"],
                },
            )

    def _send_alert(self, alert_key: str, alert_data: dict[str, Any]):
        """Send alert if not in cooldown period."""
        current_time = datetime.now(timezone.utc)

        # Check cooldown
        if alert_key in self.last_alert_times:
            time_since_last = current_time - self.last_alert_times[alert_key]
            cooldown_period = timedelta(minutes=self.config["alert_cooldown_minutes"])

            if time_since_last < cooldown_period:
                return  # Still in cooldown

        # Send alert
        alert_message = {
            "timestamp": current_time.isoformat(),
            "alert_key": alert_key,
            "level": alert_data["level"],
            "message": alert_data["message"],
            "details": alert_data,
        }

        # Log alert
        logger.warning(f"ALERT [{alert_data['level']}]: {alert_data['message']}")

        # Store in history
        self.alert_history.append(alert_message)

        # Send email if configured
        if self.config["enable_email_alerts"] and self.config["email_recipients"]:
            self._send_email_alert(alert_message)

        # Update last alert time
        self.last_alert_times[alert_key] = current_time

    def _send_email_alert(self, alert_message: dict[str, Any]):
        """Send email alert."""
        try:
            subject = f"GraphQL System Alert - {alert_message['level']}: {alert_message['message']}"

            body = f"""
GraphQL System Health Alert

Level: {alert_message['level']}
Time: {alert_message['timestamp']}
Message: {alert_message['message']}

Details:
{json.dumps(alert_message['details'], indent=2)}

This is an automated alert from the GraphQL health monitoring system.
            """

            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
                ),
                recipient_list=self.config["email_recipients"],
                fail_silently=False,
            )

            logger.info(f"Email alert sent for: {alert_message['message']}")

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def _log_health_status(self, health_report: dict[str, Any]):
        """Log current health status."""
        status = health_report["overall_status"]
        summary = health_report["summary"]

        log_message = (
            f"Health Check - Status: {status.upper()} | "
            f"Healthy: {summary['healthy']} | "
            f"Degraded: {summary['degraded']} | "
            f"Unhealthy: {summary['unhealthy']}"
        )

        if status == "healthy":
            logger.info(log_message)
        elif status == "degraded":
            logger.warning(log_message)
        else:
            logger.error(log_message)

    def get_health_summary(self) -> dict[str, Any]:
        """Get summary of recent health data."""
        if not self.health_history:
            return {"message": "No health data available"}

        recent_checks = self.health_history[-10:]  # Last 10 checks

        # Calculate averages
        total_healthy = sum(check["summary"]["healthy"] for check in recent_checks)
        total_degraded = sum(check["summary"]["degraded"] for check in recent_checks)
        total_unhealthy = sum(check["summary"]["unhealthy"] for check in recent_checks)

        # Get system metrics averages
        cpu_values = [
            check["system_metrics"].get("cpu_usage_percent", 0)
            for check in recent_checks
        ]
        memory_values = [
            check["system_metrics"].get("memory_usage_percent", 0)
            for check in recent_checks
        ]

        return {
            "monitoring_duration_minutes": len(self.health_history)
            * (self.config["check_interval_seconds"] / 60),
            "total_checks": len(self.health_history),
            "recent_checks": len(recent_checks),
            "average_healthy_components": total_healthy / len(recent_checks)
            if recent_checks
            else 0,
            "average_degraded_components": total_degraded / len(recent_checks)
            if recent_checks
            else 0,
            "average_unhealthy_components": total_unhealthy / len(recent_checks)
            if recent_checks
            else 0,
            "average_cpu_usage": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
            "average_memory_usage": sum(memory_values) / len(memory_values)
            if memory_values
            else 0,
            "total_alerts": len(self.alert_history),
            "recent_alerts": len(
                [
                    a
                    for a in self.alert_history
                    if datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                    > datetime.now(timezone.utc) - timedelta(hours=1)
                ]
            ),
        }


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
