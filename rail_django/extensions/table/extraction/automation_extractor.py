"""Automation extraction entrypoint."""

from .action_policy_extractor import extract_action_policies
from .column_policy_extractor import extract_column_policies
from .filter_policy_extractor import extract_filter_policies


def extract_automation(model_cls) -> dict:
    return {
        "columns": extract_column_policies(model_cls),
        "actions": extract_action_policies(model_cls),
        "filters": extract_filter_policies(model_cls),
    }
