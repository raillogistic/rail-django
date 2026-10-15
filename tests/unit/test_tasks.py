"""
Unit tests for background task orchestration.
"""

import graphene
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from rail_django.extensions.tasks import TaskExecution, task_mutation
from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = pytest.mark.unit


@task_mutation(name="run_task", track_progress=True)
def run_task(root, info, message: str):
    info.context.task.update_progress(50)
    return {"message": message}


class TaskMutations(graphene.ObjectType):
    run_task = run_task


class TestTaskOrchestration(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="task_user",
            password="password",
        )
        self.other_user = user_model.objects.create_user(
            username="task_user_2",
            password="password",
        )
        settings = {
            "schema_settings": {
                "mutation_extensions": [
                    "tests.unit.test_tasks.TaskMutations"
                ],
            },
            "task_settings": {
                "enabled": True,
                "backend": "sync",
                "emit_subscriptions": False,
            },
            "query_settings": {
                "default_page_size": 1,
                "max_page_size": 2,
            },
        }
        harness = build_schema(
            schema_name="task_test",
            models=["rail_django.TaskExecution"],
            apps=["rail_django"],
            settings=settings,
        )
        self.schema = harness.schema

    def _client(self, user):
        return RailGraphQLTestClient(
            self.schema,
            schema_name="task_test",
            user=user,
        )

    def test_task_mutation_runs_sync(self):
        client = self._client(self.user)
        mutation = """
        mutation {
          runTask(message: "hello") {
            taskId
            status
            task {
              status
              progress
              result
            }
          }
        }
        """
        result = client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["runTask"]
        task_id = payload["taskId"]

        self.assertEqual(payload["status"], "SUCCESS")
        self.assertEqual(payload["task"]["status"], "SUCCESS")
        self.assertEqual(payload["task"]["progress"], 100)
        task = TaskExecution.objects.get(pk=task_id)
        self.assertEqual(payload["task"]["result"], {"message": "hello"})
        self.assertEqual(task.status, "SUCCESS")
        self.assertEqual(task.progress, 100)
        self.assertEqual(task.result, {"message": "hello"})

    def test_task_query_scoped_to_owner(self):
        client = self._client(self.user)
        mutation = """
        mutation {
          runTask(message: "private") {
            taskId
          }
        }
        """
        result = client.execute(mutation)
        task_id = result["data"]["runTask"]["taskId"]

        other_client = self._client(self.other_user)
        query = f"""
        query {{
          task(id: "{task_id}") {{
            id
          }}
        }}
        """
        other_result = other_client.execute(query)
        self.assertIsNotNone(other_result.get("errors"))

    def test_task_list_filters_in_database_and_caps_limit(self):
        for index in range(3):
            TaskExecution.objects.create(
                name=f"visible-{index}",
                owner_id=str(self.user.id),
                metadata={"schema_name": "task_test"},
            )
        TaskExecution.objects.create(
            name="expired",
            owner_id=str(self.user.id),
            metadata={"schema_name": "task_test"},
            expires_at=timezone.now(),
        )
        TaskExecution.objects.create(
            name="other-schema",
            owner_id=str(self.user.id),
            metadata={"schema_name": "other"},
        )

        result = self._client(self.user).execute("query { tasks(limit: 999) { name } }")

        self.assertIsNone(result.get("errors"))
        self.assertEqual(len(result["data"]["tasks"]), 2)
        self.assertTrue(
            all(task["name"].startswith("visible-") for task in result["data"]["tasks"])
        )
