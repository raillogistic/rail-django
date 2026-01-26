"""
Tests for the CSRF bootstrap endpoint.
"""

import json

from django.conf import settings
from django.test import Client, TestCase


class CsrfEndpointTestCase(TestCase):
    """Validate the default /csrf/ endpoint behavior."""

    def setUp(self):
        self.client = Client()

    def test_csrf_endpoint_returns_token_and_cookie(self):
        response = self.client.get("/csrf/")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)

        self.assertIn("csrfToken", payload)
        self.assertTrue(payload["csrfToken"])
        self.assertEqual(response.get("X-CSRFToken"), payload["csrfToken"])

        cookie_name = getattr(settings, "CSRF_COOKIE_NAME", "csrftoken")
        self.assertIn(cookie_name, response.cookies)
