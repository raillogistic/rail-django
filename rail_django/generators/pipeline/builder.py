"""
Pipeline Builder - Builds mutation pipelines with configurable steps.

Provides a fluent interface for constructing mutation pipelines with
all necessary steps for create, update, and delete operations.
"""

from typing import Any, List, Optional, Type

from .base import MutationStep, MutationPipeline
from .steps.authentication import AuthenticationStep
from .steps.permissions import ModelPermissionStep, OperationGuardStep
from .steps.sanitization import InputSanitizationStep
from .steps.normalization import (
    EnumNormalizationStep,
    RelationOperationProcessingStep,
    ReadOnlyFieldFilterStep,
)
from .steps.validation import (
    InputValidationStep,
    NestedLimitValidationStep,
    NestedDataValidationStep,
)
from .steps.tenant import TenantInjectionStep
from .steps.lookup import InstanceLookupStep
from .steps.execution import CreateExecutionStep, UpdateExecutionStep, DeleteExecutionStep
from .steps.audit import AuditStep
from .steps.created_by import CreatedByStep

if type(None):
    from django.db import models


class PipelineBuilder:
    """
    Builds mutation pipelines with configurable steps.

    The builder provides methods to construct pipelines for create,
    update, and delete operations. Steps can be added, removed, or
    reordered as needed.

    Example:
        builder = PipelineBuilder(settings)
        builder.add_step(MyCustomStep())

        pipeline = builder.build_create_pipeline(
            model=MyModel,
            nested_handler=handler,
            input_validator=validator,
        )

        ctx = MutationContext(...)
        result = pipeline.execute(ctx)
    """

    def __init__(self, settings: Optional[Any] = None):
        """
        Initialize pipeline builder.

        Args:
            settings: Optional MutationGeneratorSettings for configuration
        """
        self.settings = settings
        self._custom_steps: List[MutationStep] = []
        self._skip_steps: List[str] = []
        self._require_authentication = True
        self._require_model_permissions = True

    def add_step(self, step: MutationStep) -> "PipelineBuilder":
        """
        Add a custom step to the pipeline.

        Args:
            step: MutationStep instance to add

        Returns:
            Self for method chaining
        """
        self._custom_steps.append(step)
        return self

    def skip_step(self, step_name: str) -> "PipelineBuilder":
        """
        Skip a step by name.

        Args:
            step_name: Name of the step to skip

        Returns:
            Self for method chaining
        """
        self._skip_steps.append(step_name)
        return self

    def require_authentication(self, require: bool = True) -> "PipelineBuilder":
        """
        Configure authentication requirement.

        Args:
            require: If True, require authenticated users

        Returns:
            Self for method chaining
        """
        self._require_authentication = require
        return self

    def require_model_permissions(self, require: bool = True) -> "PipelineBuilder":
        """
        Configure model permission requirement.

        Args:
            require: If True, enforce Django model permissions

        Returns:
            Self for method chaining
        """
        self._require_model_permissions = require
        return self

    def _filter_steps(self, steps: List[MutationStep]) -> List[MutationStep]:
        """
        Filter out skipped steps.

        Args:
            steps: List of steps to filter

        Returns:
            Filtered list of steps
        """
        if not self._skip_steps:
            return steps
        return [s for s in steps if s.name not in self._skip_steps]

    def build_create_pipeline(
        self,
        model: type["models.Model"],
        nested_handler: Optional[Any] = None,
        input_validator: Optional[Any] = None,
        tenant_applicator: Optional[Any] = None,
    ) -> MutationPipeline:
        """
        Build pipeline for create mutations.

        Args:
            model: Django model class
            nested_handler: Optional NestedOperationHandler
            input_validator: Optional input validator
            tenant_applicator: Optional tenant applicator

        Returns:
            Configured MutationPipeline
        """
        steps = [
            AuthenticationStep(self._require_authentication),
            ModelPermissionStep(self._require_model_permissions),
            OperationGuardStep(),
            InputSanitizationStep(),
            EnumNormalizationStep(),
            RelationOperationProcessingStep(),
            ReadOnlyFieldFilterStep(),
            CreatedByStep(),
            TenantInjectionStep(tenant_applicator),
            InputValidationStep(input_validator),
            NestedLimitValidationStep(nested_handler),
            NestedDataValidationStep(nested_handler),
            CreateExecutionStep(nested_handler),
            AuditStep(),
            *self._custom_steps,
        ]
        return MutationPipeline(self._filter_steps(steps))

    def build_update_pipeline(
        self,
        model: type["models.Model"],
        nested_handler: Optional[Any] = None,
        input_validator: Optional[Any] = None,
        tenant_applicator: Optional[Any] = None,
    ) -> MutationPipeline:
        """
        Build pipeline for update mutations.

        Args:
            model: Django model class
            nested_handler: Optional NestedOperationHandler
            input_validator: Optional input validator
            tenant_applicator: Optional tenant applicator

        Returns:
            Configured MutationPipeline
        """
        steps = [
            AuthenticationStep(self._require_authentication),
            ModelPermissionStep(self._require_model_permissions),
            InstanceLookupStep(tenant_applicator),  # Lookup before guard
            OperationGuardStep(),  # Guard can check instance
            InputSanitizationStep(),
            EnumNormalizationStep(),
            RelationOperationProcessingStep(),
            ReadOnlyFieldFilterStep(),
            TenantInjectionStep(tenant_applicator),
            InputValidationStep(input_validator),
            NestedLimitValidationStep(nested_handler),
            NestedDataValidationStep(nested_handler),
            UpdateExecutionStep(nested_handler),
            AuditStep(),
            *self._custom_steps,
        ]
        return MutationPipeline(self._filter_steps(steps))

    def build_delete_pipeline(
        self,
        model: type["models.Model"],
        tenant_applicator: Optional[Any] = None,
    ) -> MutationPipeline:
        """
        Build pipeline for delete mutations.

        Args:
            model: Django model class
            tenant_applicator: Optional tenant applicator

        Returns:
            Configured MutationPipeline
        """
        steps = [
            AuthenticationStep(self._require_authentication),
            ModelPermissionStep(self._require_model_permissions),
            InstanceLookupStep(tenant_applicator),
            OperationGuardStep(),
            DeleteExecutionStep(),
            AuditStep(),
            *self._custom_steps,
        ]
        return MutationPipeline(self._filter_steps(steps))

    def build_custom_pipeline(
        self,
        steps: List[MutationStep],
    ) -> MutationPipeline:
        """
        Build a custom pipeline with specified steps.

        Args:
            steps: List of MutationStep instances

        Returns:
            Configured MutationPipeline
        """
        all_steps = [*steps, *self._custom_steps]
        return MutationPipeline(self._filter_steps(all_steps))
