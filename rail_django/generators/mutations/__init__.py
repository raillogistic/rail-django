"""
Mutation Generation System Package.
"""

from .generator import MutationGenerator
from .base import TenantMixin
from .bulk import (
    generate_bulk_create_mutation,
    generate_bulk_update_mutation,
    generate_bulk_delete_mutation,
)
from .errors import (
    MutationError,
    build_error_list,
    build_integrity_errors,
    build_mutation_error,
    build_validation_errors,
)
from .methods import (
    convert_method_to_mutation,
    generate_method_mutation,
)

__all__ = [
    "MutationGenerator",
    "TenantMixin",
    "generate_bulk_create_mutation",
    "generate_bulk_update_mutation",
    "generate_bulk_delete_mutation",
    "MutationError",
    "build_error_list",
    "build_integrity_errors",
    "build_mutation_error",
    "build_validation_errors",
    "convert_method_to_mutation",
    "generate_method_mutation",
]
