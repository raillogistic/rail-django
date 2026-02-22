#!/usr/bin/env python
import os
import sys
import shutil
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
            if not getattr(parsed_startproject, "extensions", None):
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
                # 1. Copy documentation
                try:
                    docs_src = resources.files("rail_django").joinpath("docs")
                    if os.path.exists(os.fspath(docs_src)):
                        docs_dest = os.path.join(destination, "docs")
                        if not os.path.exists(docs_dest):
                            shutil.copytree(os.fspath(docs_src), docs_dest)
                except Exception as doc_err:
                    print(f"Warning: Could not copy documentation: {doc_err}")

                # 2. Rename template files
                for root, _, files in os.walk(destination):
                    for filename in files:
                        if filename.endswith("-tpl"):
                            old_path = os.path.join(root, filename)
                            new_path = os.path.join(root, filename[:-4])  # Remove -tpl

                            if not os.path.exists(new_path):
                                os.rename(old_path, new_path)
                            else:
                                os.remove(old_path)
                        elif filename.endswith(".tpl"):
                            # Also handle .tpl if any exist (like .py-tpl, just in case)
                            old_path = os.path.join(root, filename)
                            new_path = os.path.join(root, filename[:-4])  # Remove .tpl
                            if not os.path.exists(new_path):
                                os.rename(old_path, new_path)
                            else:
                                os.remove(old_path)
        except Exception as e:
            # Don't crash the tool if cleanup fails, just warn or ignore
            print(f"Warning: Post-processing failed: {e}")


if __name__ == "__main__":
    main()
