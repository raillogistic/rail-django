#!/usr/bin/env python
import os
import sys
from django.core.management import execute_from_command_line


def main():
    """Run administrative tasks."""
    # This entry point is for the 'rail-admin' command.
    # It mimics django-admin but injects our framework's defaults.

    argv = sys.argv[:]

    if len(argv) > 1 and argv[1] == "startproject":
        # Inject our custom template if the user hasn't specified one
        has_template = any(arg.startswith("--template") for arg in argv)
        if not has_template:
            import rail_django

            template_path = os.path.join(
                os.path.dirname(rail_django.__file__), "conf", "project_template"
            )
            argv.append(f"--template={template_path}")

            # If no extensions are provided, we might want to ensure .py-tpl are rendered
            # But Django handles this automatically for --template
            # However, we need to ensure the target files are named correctly.
            # We used .py-tpl, so we need to tell startproject to process them if they weren't the default.
            # Django's default is 'py,py-tpl,txt,md,html,xml,js,json,css,rc,yml,yaml,toml,ini'.
            # That covers our needs.

    execute_from_command_line(argv)


if __name__ == "__main__":
    main()
