from __future__ import annotations

import importlib.util
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


def test_main_customizes_minimal_repo_and_preserves_self_tests(
    customize_template, tmp_path: Path
) -> None:
    repo_root = _minimal_fake_repo(tmp_path)

    result = customize_template.main(["customer_agent"], repo_root)

    assert result == 0
    assert (repo_root / "src" / "customer_agent").exists()
    assert not (repo_root / "src" / "databricks_tool_agent_template").exists()
    assert (repo_root / "pyproject.toml").read_text(encoding="utf-8") == (
        'name = "customer-agent"\npackages = ["src/customer_agent"]\n'
    )
    assert "customer_agent" in (repo_root / "README.md").read_text(encoding="utf-8")
    assert "databricks_tool_agent_template" in (
        repo_root / "scripts" / "customize_template.py"
    ).read_text(encoding="utf-8")
    assert "databricks_tool_agent_template" in (
        repo_root / "tests" / "unit" / "test_customize_template.py"
    ).read_text(encoding="utf-8")


def test_main_preflight_prevents_partial_mutation_when_target_exists(
    customize_template, tmp_path: Path
) -> None:
    repo_root = _minimal_fake_repo(tmp_path)
    (repo_root / "src" / "customer_agent").mkdir()

    with pytest.raises(SystemExit) as exc_info:
        customize_template.main(["customer_agent"], repo_root)

    assert exc_info.value.code == 2
    assert (repo_root / "src" / "databricks_tool_agent_template").exists()
    assert (repo_root / "pyproject.toml").read_text(encoding="utf-8") == (
        'name = "databricks-tool-agent-template"\n'
        'packages = ["src/databricks_tool_agent_template"]\n'
    )
    assert "databricks_tool_agent_template" in (repo_root / "README.md").read_text(encoding="utf-8")


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


@pytest.mark.parametrize(
    "package_name",
    [
        "customer-agent",
        "CustomerAgent",
        "1customer_agent",
        "class",
    ],
)
def test_main_rejects_invalid_package_names_without_mutation(
    customize_template,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    package_name: str,
) -> None:
    repo_root = _minimal_fake_repo(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        customize_template.main([package_name], repo_root)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "lowercase snake_case" in captured.err
    assert "Traceback" not in captured.err
    assert (repo_root / "src" / "databricks_tool_agent_template").exists()
    assert "databricks_tool_agent_template" in (repo_root / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def _minimal_fake_repo(tmp_path: Path) -> Path:
    package_dir = tmp_path / "src" / "databricks_tool_agent_template"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    (tmp_path / "pyproject.toml").write_text(
        'name = "databricks-tool-agent-template"\n'
        'packages = ["src/databricks_tool_agent_template"]\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "Use databricks_tool_agent_template from databricks-tool-agent-template.\n",
        encoding="utf-8",
    )

    script = tmp_path / "scripts" / "customize_template.py"
    script.parent.mkdir()
    script.write_text(
        'TEMPLATE_PACKAGE = "databricks_tool_agent_template"\n',
        encoding="utf-8",
    )

    test = tmp_path / "tests" / "unit" / "test_customize_template.py"
    test.parent.mkdir(parents=True)
    test.write_text(
        'assert "databricks_tool_agent_template"\n',
        encoding="utf-8",
    )

    return tmp_path
