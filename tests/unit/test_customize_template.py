from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "customize_template.py"


@pytest.fixture(scope="module")
def customize_template():
    spec = importlib.util.spec_from_file_location("customize_template", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "package_name",
    [
        "my_agent_app",
        "agent",
        "agent2_app",
    ],
)
def test_validate_package_name_accepts_snake_case(customize_template, package_name: str) -> None:
    customize_template.validate_package_name(package_name)


@pytest.mark.parametrize(
    "package_name",
    [
        "my-agent-app",
        "my agent app",
        "my.agent.app",
        "1agent",
        "class",
        "MyAgent",
        "_agent",
    ],
)
def test_validate_package_name_rejects_invalid_names(customize_template, package_name: str) -> None:
    with pytest.raises(ValueError, match="lowercase snake_case"):
        customize_template.validate_package_name(package_name)


def test_replace_text_in_repo_rewrites_template_strings(customize_template, tmp_path: Path) -> None:
    sample = tmp_path / "pyproject.toml"
    sample.write_text(
        "\n".join(
            [
                'name = "databricks-tool-agent-template"',
                'packages = ["src/databricks_tool_agent_template"]',
            ]
        ),
        encoding="utf-8",
    )

    customize_template.replace_text_in_repo(
        customize_template.TEMPLATE_PACKAGE, "my_agent_app", tmp_path
    )
    customize_template.replace_text_in_repo(
        customize_template.TEMPLATE_DISTRIBUTION, "my-agent-app", tmp_path
    )

    assert sample.read_text(encoding="utf-8") == (
        'name = "my-agent-app"\npackages = ["src/my_agent_app"]'
    )


def test_replace_text_in_repo_rewrites_customization_script(
    customize_template, tmp_path: Path
) -> None:
    script = tmp_path / "scripts" / "customize_template.py"
    script.parent.mkdir()
    script.write_text(
        (
            'TEMPLATE_PACKAGE = "databricks_tool_agent_template"\n'
            'TEMPLATE_DISTRIBUTION = "databricks-tool-agent-template"\n'
        ),
        encoding="utf-8",
    )

    customize_template.replace_text_in_repo(
        customize_template.TEMPLATE_PACKAGE, "my_agent_app", tmp_path
    )
    customize_template.replace_text_in_repo(
        customize_template.TEMPLATE_DISTRIBUTION, "my-agent-app", tmp_path
    )

    assert script.read_text(encoding="utf-8") == (
        'TEMPLATE_PACKAGE = "my_agent_app"\nTEMPLATE_DISTRIBUTION = "my-agent-app"\n'
    )


def test_rename_package_dir_moves_template_package(customize_template, tmp_path: Path) -> None:
    package_dir = tmp_path / "src" / customize_template.TEMPLATE_PACKAGE
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    customize_template.rename_package_dir("my_agent_app", tmp_path)

    assert not package_dir.exists()
    assert (tmp_path / "src" / "my_agent_app" / "__init__.py").exists()


def test_replace_text_in_repo_skips_ignored_directories(customize_template, tmp_path: Path) -> None:
    tracked_file = tmp_path / "README.md"
    tracked_file.write_text(customize_template.TEMPLATE_PACKAGE, encoding="utf-8")

    git_file = tmp_path / ".git" / "config"
    git_file.parent.mkdir()
    git_file.write_text(customize_template.TEMPLATE_PACKAGE, encoding="utf-8")

    cache_file = tmp_path / "__pycache__" / "module.py"
    cache_file.parent.mkdir()
    cache_file.write_text(customize_template.TEMPLATE_PACKAGE, encoding="utf-8")

    customize_template.replace_text_in_repo(
        customize_template.TEMPLATE_PACKAGE, "my_agent_app", tmp_path
    )

    assert tracked_file.read_text(encoding="utf-8") == "my_agent_app"
    assert git_file.read_text(encoding="utf-8") == customize_template.TEMPLATE_PACKAGE
    assert cache_file.read_text(encoding="utf-8") == customize_template.TEMPLATE_PACKAGE


def test_main_reports_invalid_package_name_without_traceback(
    customize_template, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["customize_template.py", "my-agent-app"])

    with pytest.raises(SystemExit) as exc_info:
        customize_template.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "lowercase snake_case" in captured.err
    assert "Traceback" not in captured.err
