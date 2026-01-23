"""
Unit tests for background task orchestration.
"""

import graphene
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

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
                    "rail_django.tests.unit.test_tasks.TaskMutations"
                ],
            },
            "task_settings": {
                "enabled": True,
                "backend": "sync",
                "emit_subscriptions": False,
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

