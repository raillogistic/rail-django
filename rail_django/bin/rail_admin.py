#!/usr/bin/env python
import os
import sys
import shutil
from importlib import resources
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

            template_path = resources.files("rail_django").joinpath(
                "scaffolding", "project_template"
            )
            argv.append(f"--template={os.fspath(template_path)}")
            
            # Ensure our custom template extensions are processed and renamed
            # .py-tpl -> .py and .txt-tpl -> .txt
            has_extension = any(arg.startswith("--extension") or arg.startswith("-e") for arg in argv)
            if not has_extension:
                argv.append("--extension=py-tpl,txt-tpl")

    execute_from_command_line(argv)

    # Post-processing: Rename *-tpl files and copy docs
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
                # 1. Copy documentation
                try:
                    import rail_django
                    docs_src = resources.files("rail_django").joinpath("docs")
                    if os.path.exists(os.fspath(docs_src)):
                        docs_dest = os.path.join(destination, "docs")
                        if not os.path.exists(docs_dest):
                            shutil.copytree(os.fspath(docs_src), docs_dest)
                except Exception as doc_err:
                    print(f"Warning: Could not copy documentation: {doc_err}")

                # 2. Rename template files
                for root, dirs, files in os.walk(destination):
                    for filename in files:
                        if filename.endswith('-tpl'):
                            old_path = os.path.join(root, filename)
                            new_path = os.path.join(root, filename[:-4]) # Remove -tpl
                            
                            if not os.path.exists(new_path):
                                os.rename(old_path, new_path)
                            else:
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
            print(f"Warning: Post-processing failed: {e}")


if __name__ == "__main__":
    main()
