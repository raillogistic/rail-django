"""
Mutation Pipeline Architecture.

This module provides a composable, testable pipeline for handling GraphQL mutations.

Core Components:
- MutationContext: Carries state through the pipeline
- MutationStep: Abstract base for each pipeline step
- MutationPipeline: Orchestrates step execution
- PipelineBuilder: Builds pipelines with configurable steps

Usage:
    from rail_django.generators.pipeline import PipelineBuilder, MutationContext

    builder = PipelineBuilder(settings)
    pipeline = builder.build_create_pipeline(model, nested_handler=handler)

    ctx = MutationContext(info=info, model=Model, operation="create", ...)
    result_ctx = pipeline.execute(ctx)
"""

from .context import MutationContext
from .base import MutationStep, MutationPipeline, ConditionalStep
from .builder import PipelineBuilder

__all__ = [
    "MutationContext",
    "MutationStep",
    "MutationPipeline",
    "ConditionalStep",
    "PipelineBuilder",
]
