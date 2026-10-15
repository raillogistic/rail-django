"""Handled pipeline validation failures must roll back earlier nested writes."""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rail_django.generators.pipeline.factories.base import BasePipelineMutation


class RejectedNestedMutation(BasePipelineMutation):
    """Simulate a valid first child followed by a rejected child."""

    model_class = User
    operation = "create"

    @classmethod
    def build_context(cls, info, input_data, instance_id=None):
        """Keep this regression focused on the transaction boundary."""
        return None

    @classmethod
    def execute_pipeline(cls, context):
        """Write one child before ordinary model validation rejects the next."""
        User.objects.create(username="pipeline-rollback-regression")
        raise ValidationError({"nomenclature": "Article non autorisé"})


@pytest.mark.unit
@pytest.mark.django_db
def test_handled_validation_error_rolls_back_nested_writes():
    """An ok=false response cannot commit successful earlier steps."""
    response = RejectedNestedMutation.mutate(None, None, input={})
    assert response.ok is False
    assert not User.objects.filter(username="pipeline-rollback-regression").exists()
