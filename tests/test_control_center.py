"""Integration tests for control center pages and APIs."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rail_django.models import MediaExportJob, MediaExportJobStatus


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
        self.assertContains(response, "Export Media (ZIP)")

    def test_capacity_cost_page_renders_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/control-center/capacity-cost/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Capacity &amp; Cost")

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

    def test_capacity_cost_api_returns_usage_tables(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir, "mediafiles")
            logs_dir = Path(temp_dir, "logs")
            backups_dir = Path(temp_dir, "backups")
            media_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            backups_dir.mkdir(parents=True, exist_ok=True)
            Path(media_dir, "photo.jpg").write_bytes(b"x" * 1024)
            Path(logs_dir, "django.log").write_text("hello", encoding="utf-8")
            Path(backups_dir, "backup_20260301_100000.dump").write_bytes(b"PGDMP")

            with patch.dict(
                os.environ, {"BACKUP_PATH": str(backups_dir)}, clear=False
            ):
                with override_settings(MEDIA_ROOT=str(media_dir), LOGGING_DIR=str(logs_dir)):
                    response = self.client.get(
                        "/control-center/api/capacity-cost/",
                        HTTP_ACCEPT="application/json",
                    )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["section"], "capacity-cost")
        tables = body["payload"]["tables"]
        titles = {table["title"] for table in tables}
        self.assertIn("Area usage", titles)
        self.assertIn("Top consumers", titles)
        self.assertIn("Largest files", titles)

    def test_backups_api_exposes_download_link(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_name = "backup_20260301_120000.dump"
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
            "/control-center/backups/download/backup_20260301_120000.dump/"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_backup_download_returns_file_for_superuser(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_name = "backup_20260301_120000.dump"
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
            Path(out_file).write_bytes(b"PGDMP-mock-custom-dump")
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
        self.assertTrue(download_bytes.startswith(b"PGDMP"))
        self.assertIn(".dump", response["Content-Disposition"])

    def test_media_entries_api_requires_authentication(self):
        response = self.client.get(
            "/control-center/api/media-export/entries/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_media_entries_api_returns_top_level_entries_preselected(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as media_dir:
            Path(media_dir, "invoices").mkdir(parents=True, exist_ok=True)
            Path(media_dir, "logo.png").write_bytes(b"png-data")
            Path(media_dir, "invoices", "invoice-1.pdf").write_bytes(b"pdf-data")

            with override_settings(MEDIA_ROOT=media_dir):
                response = self.client.get(
                    "/control-center/api/media-export/entries/",
                    HTTP_ACCEPT="application/json",
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        entries = payload["entries"]
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(item["selected_default"] for item in entries))
        entry_ids = {item["id"] for item in entries}
        self.assertIn("invoices", entry_ids)
        self.assertIn("logo.png", entry_ids)

    def test_media_job_create_rejects_empty_selection(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            "/control-center/media-export/jobs/",
            data=json.dumps({"selected_entry_ids": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_media_job_create_enqueues_job(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as media_dir:
            Path(media_dir, "docs").mkdir(parents=True, exist_ok=True)
            Path(media_dir, "docs", "a.txt").write_text("hello", encoding="utf-8")
            with override_settings(MEDIA_ROOT=media_dir):
                with patch(
                    "rail_django.http.views.control_center._start_media_export_job"
                ) as mocked_start:
                    response = self.client.post(
                        "/control-center/media-export/jobs/",
                        data=json.dumps({"selected_entry_ids": ["docs"]}),
                        content_type="application/json",
                    )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], MediaExportJobStatus.PENDING)
        self.assertTrue(MediaExportJob.objects.filter(pk=body["job_id"]).exists())
        mocked_start.assert_called_once()

    def test_media_job_status_returns_download_url_when_ready(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir, "media_exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            archive_name = "media_export_20260301_130000_aaaa1111.zip"
            archive_path = export_dir / archive_name
            archive_path.write_bytes(b"zip-bytes")

            job = MediaExportJob.objects.create(
                requested_by=self.superuser,
                status=MediaExportJobStatus.SUCCESS,
                progress=100,
                selected_paths=["docs"],
                archive_name=archive_name,
                archive_path=str(archive_path),
                archive_size_bytes=archive_path.stat().st_size,
                uncompressed_size_bytes=1024,
                message="Archive ready.",
            )

            with patch.dict(os.environ, {"BACKUP_PATH": temp_dir}, clear=False):
                response = self.client.get(
                    f"/control-center/media-export/jobs/{job.id}/",
                    HTTP_ACCEPT="application/json",
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], MediaExportJobStatus.SUCCESS)
        self.assertIn(
            f"/control-center/media-export/download/{archive_name}/",
            body["download_url"],
        )

    def test_media_export_download_requires_authentication(self):
        response = self.client.get(
            "/control-center/media-export/download/media_export_20260301_130000_aaaa1111.zip/"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_media_export_download_returns_archive_for_superuser(self):
        self.client.force_login(self.superuser)
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir, "media_exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            archive_name = "media_export_20260301_130000_aaaa1111.zip"
            archive_content = b"zip-content"
            archive_path = export_dir / archive_name
            archive_path.write_bytes(archive_content)

            with patch.dict(os.environ, {"BACKUP_PATH": temp_dir}, clear=False):
                response = self.client.get(
                    f"/control-center/media-export/download/{archive_name}/"
                )
                downloaded = b"".join(response.streaming_content)
                response.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn(archive_name, response["Content-Disposition"])
        self.assertEqual(downloaded, archive_content)
