#!/usr/bin/env python
import os
import sys
import shutil
import time
from importlib import resources
from django.core.management import execute_from_command_line


def _parse_startproject_options(raw_args):
    """Parse `startproject` args using Django's own command parser."""
    from django.core.management.commands.startproject import Command as StartProjectCommand

    parser = StartProjectCommand().create_parser("rail-admin", "startproject")
    try:
        options, _ = parser.parse_known_args(raw_args)
    except SystemExit:
        return None
    return options


def _resolve_startproject_destination(options):
    """Resolve the generated project destination like Django's startproject."""
    project_name = getattr(options, "name", None)
    directory = getattr(options, "directory", None)
    if not project_name:
        return None
    if directory:
        return os.path.abspath(directory)
    return os.path.abspath(os.path.join(os.getcwd(), project_name))


def _is_scaffold_destination(path):
    """Return True when `path` looks like a freshly scaffolded project root."""
    has_manage = any(
        os.path.exists(os.path.join(path, filename))
        for filename in ("manage.py", "manage.py-tpl")
    )
    has_layout_dir = any(
        os.path.isdir(os.path.join(path, dirname))
        for dirname in ("root", "apps", "deploy")
    )
    return has_manage and has_layout_dir


def _copy_docs_if_missing(destination):
    """Copy bundled docs into the scaffolded project when absent."""
    try:
        docs_src = resources.files("rail_django").joinpath("docs")
        if os.path.exists(os.fspath(docs_src)):
            docs_dest = os.path.join(destination, "docs")
            if not os.path.exists(docs_dest):
                shutil.copytree(os.fspath(docs_src), docs_dest)
    except Exception as doc_err:
        print(f"Warning: Could not copy documentation: {doc_err}")


def _rename_template_file(old_path, new_path, retries=5):
    """Rename rendered template files with retries for transient file locks."""
    for attempt in range(retries):
        try:
            os.rename(old_path, new_path)
            return
        except PermissionError:
            if attempt >= retries - 1:
                raise
            time.sleep(0.1 * (attempt + 1))


def _post_process_scaffold(destination):
    """
    Finalize scaffold output:
    1) copy framework docs if missing
    2) rename/remove template suffix files
    """
    _copy_docs_if_missing(destination)

    failures = []
    for root, _, files in os.walk(destination):
        for filename in files:
            if filename.endswith("-tpl"):
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, filename[:-4])  # Remove -tpl
            elif filename.endswith(".tpl"):
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, filename[:-4])  # Remove .tpl
            else:
                continue

            try:
                if not os.path.exists(new_path):
                    _rename_template_file(old_path, new_path)
                else:
                    os.remove(old_path)
            except Exception as exc:
                failures.append((old_path, new_path, exc))

    if failures:
        previews = [
            f"{old} -> {new}: {err}" for old, new, err in failures[:3]
        ]
        remainder = len(failures) - len(previews)
        details = "; ".join(previews)
        if remainder > 0:
            details = f"{details}; ... ({remainder} more)"
        raise RuntimeError(f"Failed to finalize scaffold template files: {details}")


def main():
    """Run administrative tasks."""
    # This entry point is for the 'rail-admin' command.
    # It mimics django-admin but injects our framework's defaults.

    argv = sys.argv[:]
    parsed_startproject = None

    if len(argv) > 1 and argv[1] == "startproject":
        parsed_startproject = _parse_startproject_options(argv[2:])
        # Inject our custom template if the user hasn't specified one
        if parsed_startproject and not getattr(parsed_startproject, "template", None):
            template_path = resources.files("rail_django").joinpath(
                "scaffolding", "project_template"
            )
            argv.append(f"--template={os.fspath(template_path)}")

            # Ensure our custom template extensions are processed and renamed
            # .py-tpl -> .py and .txt-tpl -> .txt
            user_supplied_extensions = any(
                arg == "-e" or arg.startswith("--extension")
                for arg in argv[2:]
            )
            if not user_supplied_extensions:
                argv.append("--extension=py-tpl,txt-tpl")

    execute_from_command_line(argv)

    # Post-processing: Rename *-tpl files and copy docs
    if len(argv) > 1 and argv[1] == "startproject":
        try:
            parsed_startproject = _parse_startproject_options(argv[2:])
            if not parsed_startproject:
                return

            destination = _resolve_startproject_destination(parsed_startproject)
            if not destination or not os.path.exists(destination):
                return

            if not _is_scaffold_destination(destination):
                print(
                    "Warning: Destination does not match expected scaffold layout; "
                    "skipping post-processing."
                )
                return

            if os.path.exists(destination):
                _post_process_scaffold(destination)
        except Exception as e:
            raise SystemExit(f"Post-processing failed: {e}") from e


if __name__ == "__main__":
    main()
