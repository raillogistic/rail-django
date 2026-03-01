"""Integration tests for control center pages and APIs."""

from __future__ import annotations

import gzip
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


class ControlCenterIntegrationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            username="control-admin",
            email="admin@example.com",
            password="strong-password-123",
        )
        self.staff_user = user_model.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="strong-password-123",
            is_staff=True,
        )

    def test_page_redirects_when_not_authenticated(self):
        response = self.client.get("/control-center/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_page_forbidden_for_non_superuser(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/control-center/")
        self.assertEqual(response.status_code, 403)

    def test_page_renders_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/control-center/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rail Django Control Center")

    def test_backups_page_renders_create_download_button(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/control-center/backups/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create & Download Backup")

    def test_api_requires_authentication(self):
        response = self.client.get(
            "/control-center/api/overview/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertJSONEqual(
            response.content.decode("utf-8"),
            {"error": "Authentication required"},
        )

    def test_api_requires_superuser(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(
            "/control-center/api/overview/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertJSONEqual(
            response.content.decode("utf-8"),
            {"error": "Superuser access required"},
        )

    def test_api_returns_payload_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/control-center/api/overview/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["section"], "overview")
        self.assertIn("meta", body)
        self.assertIn("payload", body)
        self.assertIn("summary", body["payload"])

    def test_backups_api_exposes_download_link(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_name = "backup_20260301_120000.sql.gz"
            backup_file = os.path.join(temp_dir, backup_name)
            with open(backup_file, "wb") as handle:
                handle.write(b"test-backup")

            with patch.dict(os.environ, {"BACKUP_PATH": temp_dir}, clear=False):
                response = self.client.get(
                    "/control-center/api/backups/",
                    HTTP_ACCEPT="application/json",
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body["payload"]["tables"][0]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], backup_name)
        self.assertIn(
            f"/control-center/backups/download/{backup_name}/",
            rows[0]["download"],
        )

    def test_backup_download_requires_authentication(self):
        response = self.client.get(
            "/control-center/backups/download/backup_20260301_120000.sql.gz/"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_backup_download_returns_file_for_superuser(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_name = "backup_20260301_120000.sql.gz"
            backup_content = b"sample-backup-content"
            backup_file = os.path.join(temp_dir, backup_name)
            with open(backup_file, "wb") as handle:
                handle.write(backup_content)

            with patch.dict(os.environ, {"BACKUP_PATH": temp_dir}, clear=False):
                response = self.client.get(
                    f"/control-center/backups/download/{backup_name}/"
                )
                downloaded_content = b"".join(response.streaming_content)
                response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{backup_name}"',
        )
        self.assertEqual(downloaded_content, backup_content)

    def test_backup_create_download_requires_authentication(self):
        response = self.client.post("/control-center/backups/create-download/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    @override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}}
    )
    def test_backup_create_download_rejects_non_postgresql(self):
        self.client.force_login(self.superuser)
        response = self.client.post("/control-center/backups/create-download/")
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "supported only for PostgreSQL",
            response.content.decode("utf-8"),
        )

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "app_db",
                "HOST": "127.0.0.1",
                "PORT": "5432",
                "USER": "postgres",
                "PASSWORD": "postgres",
            }
        }
    )
    def test_backup_create_download_builds_new_archive_for_superuser(self):
        self.client.force_login(self.superuser)

        def _fake_pg_dump(command, **kwargs):
            out_file = None
            for arg in command:
                if str(arg).startswith("--file="):
                    out_file = str(arg).split("=", 1)[1]
                    break
            assert out_file is not None
            Path(out_file).write_text("mock-sql-dump", encoding="utf-8")
            return subprocess.CompletedProcess(args=command, returncode=0)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"BACKUP_PATH": temp_dir}, clear=False):
                with patch(
                    "rail_django.http.views.control_center.subprocess.run",
                    side_effect=_fake_pg_dump,
                ):
                    response = self.client.post(
                        "/control-center/backups/create-download/"
                    )
                    download_bytes = b"".join(response.streaming_content)
                    response.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertEqual(gzip.decompress(download_bytes), b"mock-sql-dump")
