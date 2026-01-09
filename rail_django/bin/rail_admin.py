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
            
            # Ensure our custom template extensions are processed and renamed
            # .py-tpl -> .py and .txt-tpl -> .txt
            has_extension = any(arg.startswith("--extension") or arg.startswith("-e") for arg in argv)
            if not has_extension:
                argv.append("--extension=py-tpl,txt-tpl")

    execute_from_command_line(argv)

    # Post-processing: Rename *-tpl files to remove the suffix
    # Django does not automatically rename custom extensions like .txt-tpl or .py-tpl (except for specific cases)
    if len(argv) > 1 and argv[1] == "startproject":
        try:
            # Parse arguments to find the project directory
            args = [arg for arg in argv[2:] if not arg.startswith('-')]
            if not args:
                return # Should not happen if startproject succeeded
            
            project_name = args[0]
            if len(args) > 1:
                destination = args[1]
            else:
                destination = os.path.join(os.getcwd(), project_name)
            
            destination = os.path.abspath(destination)

            if os.path.exists(destination):
                for root, dirs, files in os.walk(destination):
                    for filename in files:
                        if filename.endswith('-tpl'):
                            old_path = os.path.join(root, filename)
                            new_path = os.path.join(root, filename[:-4]) # Remove -tpl
                            
                            # If the target file already exists (e.g. Django somehow renamed it), 
                            # we skip to avoid overwriting or errors, unless we want to enforce our template.
                            # But usually, it won't exist if the filename is 'requirements.txt-tpl'.
                            if not os.path.exists(new_path):
                                os.rename(old_path, new_path)
                            else:
                                # If both exist, we probably want the rendered one which might be the .tpl one?
                                # Actually, if Django rendered into requirements.txt-tpl, then requirements.txt shouldn't exist.
                                # Just in case, we remove the .tpl file if the clean one exists to keep it clean.
                                os.remove(old_path)
                        elif filename.endswith('.tpl'):
                             # Also handle .tpl if any exist (like .py-tpl which Django usually handles, but just in case)
                            old_path = os.path.join(root, filename)
                            new_path = os.path.join(root, filename[:-4]) # Remove .tpl
                            if not os.path.exists(new_path):
                                os.rename(old_path, new_path)
                            else:
                                os.remove(old_path)
        except Exception as e:
            # Don't crash the tool if cleanup fails, just warn or ignore
            print(f"Warning: Could not cleanup template files: {e}")


if __name__ == "__main__":
    main()
