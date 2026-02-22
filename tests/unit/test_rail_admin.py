"""
Unit tests for rail_admin CLI tool.
"""

import sys
from unittest.mock import patch
import pytest
from rail_django.bin.rail_admin import main, _post_process_scaffold

pytestmark = pytest.mark.unit

class TestRailAdmin:
    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    def test_main_startproject_injects_template(self, mock_execute):
        """Test that startproject command injects the custom template."""
        with patch.object(sys, "argv", ["rail-admin", "startproject", "myproject"]):
            main()
            
            args, _ = mock_execute.call_args
            argv = args[0]
            
            assert "startproject" in argv
            assert "myproject" in argv
            assert any(arg.startswith("--template=") for arg in argv)
            assert "--extension=py-tpl,txt-tpl" in argv
            
            # Verify template path points to rail_django/scaffolding/project_template
            template_arg = next(arg for arg in argv if arg.startswith("--template="))
            assert "project_template" in template_arg

    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    def test_main_startproject_preserves_existing_template(self, mock_execute):
        """Test that user-provided template is not overridden."""
        custom_template = "/path/to/custom/template"
        with patch.object(sys, "argv", ["rail-admin", "startproject", "myproject", f"--template={custom_template}"]):
            main()
            
            args, _ = mock_execute.call_args
            argv = args[0]
            
            template_args = [arg for arg in argv if arg.startswith("--template=")]
            assert len(template_args) == 1
            assert template_args[0] == f"--template={custom_template}"

    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    def test_main_startproject_preserves_existing_extensions(self, mock_execute):
        """Test that user-provided template extensions are not overridden."""
        extension_arg = "--extension=jinja,py"
        with patch.object(
            sys,
            "argv",
            ["rail-admin", "startproject", "myproject", extension_arg],
        ):
            main()

            args, _ = mock_execute.call_args
            argv = args[0]

            assert extension_arg in argv
            assert "--extension=py-tpl,txt-tpl" not in argv

    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    def test_main_other_commands_untouched(self, mock_execute):
        """Test that other commands are passed through without modification."""
        with patch.object(sys, "argv", ["rail-admin", "migrate"]):
            main()
            
            args, _ = mock_execute.call_args
            argv = args[0]
            
            assert argv == ["rail-admin", "migrate"]
            assert not any(arg.startswith("--template=") for arg in argv)

    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    @patch("os.walk")
    @patch("os.path.exists")
    @patch("os.rename")
    @patch("os.remove")
    @patch("rail_django.bin.rail_admin._is_scaffold_destination", return_value=True)
    def test_post_processing_renames_templates(self, mock_scaffold_check, mock_remove, mock_rename, mock_exists, mock_walk, mock_execute):
        """Test that post-processing renames .tpl files."""
        # Setup mocks
        mock_exists.return_value = True
        mock_walk.return_value = [
            ("/path/to/project", [], ["file.py-tpl", "requirements.txt-tpl", "normal.py"])
        ]
        
        # Scenario: Clean target files don't exist yet
        def exists_side_effect(path):
            if path.endswith("-tpl"):
                return True
            if path == "/path/to/project":
                return True
            if path in {
                "/path/to/project/manage.py",
                "/path/to/project/root",
                "/path/to/project/apps",
                "/path/to/project/deploy",
            }:
                return True
            return False
        
        mock_exists.side_effect = exists_side_effect

        with patch.object(sys, "argv", ["rail-admin", "startproject", "myproject"]):
            with patch("os.path.abspath", return_value="/path/to/project"):
                main()
            
            # Verify renames
            calls = mock_rename.call_args_list
            assert len(calls) == 2
            
            # Check for file.py-tpl -> file.py
            call1_args = calls[0][0]
            assert "file.py-tpl" in call1_args[0]
            assert "file.py" in call1_args[1]
            
            # Check for requirements.txt-tpl -> requirements.txt
            call2_args = calls[1][0]
            assert "requirements.txt-tpl" in call2_args[0]
            assert "requirements.txt" in call2_args[1]

    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    @patch("os.walk")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("rail_django.bin.rail_admin._is_scaffold_destination", return_value=True)
    def test_post_processing_cleans_duplicates(self, mock_scaffold_check, mock_remove, mock_exists, mock_walk, mock_execute):
        """Test that .tpl files are removed if target already exists."""
        # Setup mocks
        mock_exists.return_value = True
        mock_walk.return_value = [
            ("/path/to/project", [], ["file.py-tpl"])
        ]
        
        # Scenario: Both files exist
        mock_exists.side_effect = lambda path: True

        with patch.object(sys, "argv", ["rail-admin", "startproject", "myproject"]):
            main()
            
            # Verify remove is called instead of rename
            mock_remove.assert_called_once()
            args, _ = mock_remove.call_args
            assert "file.py-tpl" in args[0]

    @patch("rail_django.bin.rail_admin._copy_docs_if_missing")
    def test_post_process_scaffold_renames_templates_on_real_filesystem(self, _mock_docs, tmp_path):
        """Test that post-processing renames template files on a real filesystem."""
        destination = tmp_path / "demo_project"
        destination.mkdir()
        template_file = destination / "requirements.txt-tpl"
        template_file.write_text("demo", encoding="utf-8")

        _post_process_scaffold(str(destination))

        assert not template_file.exists()
        assert (destination / "requirements.txt").read_text(encoding="utf-8") == "demo"

    @patch("rail_django.bin.rail_admin.execute_from_command_line")
    @patch("rail_django.bin.rail_admin._post_process_scaffold", side_effect=RuntimeError("boom"))
    @patch("rail_django.bin.rail_admin._is_scaffold_destination", return_value=True)
    @patch("os.path.exists", return_value=True)
    @patch("os.path.abspath", return_value="/path/to/project")
    def test_post_processing_failure_exits_non_zero(
        self,
        _mock_abspath,
        _mock_exists,
        _mock_scaffold_check,
        _mock_post_process,
        _mock_execute,
    ):
        """Test that post-processing failures stop the command with a non-zero exit."""
        with patch.object(sys, "argv", ["rail-admin", "startproject", "myproject"]):
            with pytest.raises(SystemExit, match="Post-processing failed: boom"):
                main()
