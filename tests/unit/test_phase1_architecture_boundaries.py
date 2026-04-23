import os
import subprocess
import sys
from pathlib import Path

import pytest

from rail_django.plugins import (
    BasePlugin,
    ExecutionHookResult,
    HookRegistry,
    PluginManager,
    hook_registry,
    plugin_manager,
)

pytestmark = pytest.mark.unit


def test_public_imports_work_without_configured_django_settings():
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("DJANGO_SETTINGS_MODULE", None)

    command = [
        sys.executable,
        "-c",
        (
            "import rail_django; "
            "import rail_django.core as core; "
            "assert rail_django.ConfigLoader.__name__ == 'ConfigLoader'; "
            "assert core.ConfigLoader.__name__ == 'ConfigLoader'; "
            "print('ok')"
        ),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_plugins_package_exports_runtime_extension_points():
    assert issubclass(BasePlugin, object)
    assert issubclass(PluginManager, object)
    assert issubclass(HookRegistry, object)
    assert isinstance(plugin_manager, PluginManager)
    assert isinstance(hook_registry, HookRegistry)

    result = ExecutionHookResult(handled=True, result="value")

    assert result.handled is True
    assert result.result == "value"
