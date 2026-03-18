import tempfile
import shutil
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    GRAPHQL_SCHEMA_API_AUTH_REQUIRED=True,
)
class ProtectedMediaApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="media_user",
            password="pass12345",
        )

    def test_requires_authentication(self):
        response = self.client.get("/api/v1/media/documents/report.pdf")

        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("Authentication required", payload["data"]["message"])

    def test_serves_media_file_for_authenticated_session(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, True)
        media_dir = Path(media_root)
        target = media_dir / "documents" / "report.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4 test payload")

        with override_settings(MEDIA_ROOT=media_root):
            self.client.force_login(self.user)
            response = self.client.get("/api/v1/media/documents/report.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get("Content-Disposition"),
            'inline; filename="report.pdf"',
        )
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 test payload")
        stream = getattr(response, "file_to_stream", None)
        if stream is not None:
            stream.close()
        response.close()

    def test_blocks_path_traversal(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.user)
                response = self.client.get("/api/v1/media/../secret.txt")

        self.assertEqual(response.status_code, 404)
