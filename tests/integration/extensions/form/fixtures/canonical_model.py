"""
Canonical operation-name fixture for generated model-form compatibility tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalModelFixture:
    app_label: str
    model_name: str

    @property
    def create_operation(self) -> str:
        return f"create{self.model_name}"

    @property
    def update_operation(self) -> str:
        return f"update{self.model_name}"

    @property
    def delete_operation(self) -> str:
        return f"delete{self.model_name}"

    @property
    def page_query(self) -> str:
        token = self.model_name[:1].lower() + self.model_name[1:]
        return f"{token}Page"


CANONICAL_PRODUCT_FIXTURE = CanonicalModelFixture(
    app_label="test_app",
    model_name="Product",
)
