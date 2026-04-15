import json
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.config import load_settings, parse_task_input_file
from databricks_mcp_agent_hello_world.models import AgentTaskRequest, ToolProfile, ToolSpec
from databricks_mcp_agent_hello_world.profiles.compiler import ToolProfileCompiler
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


def _tool(name: str, side_effect_level: str = "read_only") -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}, "required": []},
        provider_type="local_python",
        provider_id="builtin_tools",
        capability_tags=["demo"],
        side_effect_level=side_effect_level,
        data_domains=["demo"],
        example_uses=["Example"],
    )


def _settings(tmp_path: Path):
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "active_profile_name: default",
                "default_compile_task_file: examples/demo_compile_task.json",
                "storage:",
                "  tool_profile_table: main.agent.tool_profiles",
                "  agent_runs_table: main.agent.agent_runs",
                "  agent_output_table: main.agent.agent_outputs",
            ]
        ),
        encoding="utf-8",
    )
    return load_settings(str(config_path))


class StubProvider:
    def __init__(self, tools):
        self._tools = tools

    def list_tools(self):
        return self._tools

    def inventory_hash(self):
        return "inventory-hash"


class StubRepo:
    def __init__(self):
        self.saved = None

    def load_active(self, profile_name):
        return None

    def save(self, profile):
        self.saved = profile


class RecordingCompilerLLM:
    def __init__(self, decision):
        self.decision = decision
        self.complete_json_calls = []
        self.complete_text_calls = []

    def complete_json(self, system_prompt, user_prompt):
        self.complete_json_calls.append((system_prompt, user_prompt))
        return self.decision

    def complete_text(self, system_prompt, user_prompt):
        self.complete_text_calls.append((system_prompt, user_prompt))
        return "audit"


class RecordingRuntimeLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.index = 0

    def tool_step(self, messages, tools, tool_choice=None):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        response = self.responses[self.index]
        self.index += 1
        return response


class StubWriter:
    def write_run_record(self, record) -> None:
        return None

    def write_output_record(self, record) -> None:
        return None


class StubExecutor:
    def call_tool(self, tool_call):
        raise AssertionError("This test should not need to execute a tool")


class StubProfileRepoForRunner:
    def __init__(self, profile):
        self.profile = profile

    def load_active(self, profile_name):
        return self.profile


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_compiler_calls_llm_complete_json_exactly_once_for_demo_task(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = settings
    compiler.provider = StubProvider(
        [
            _tool("get_user_profile"),
            _tool("search_onboarding_docs"),
            _tool("get_workspace_setting"),
            _tool("list_recent_job_runs"),
            _tool("create_support_ticket", side_effect_level="write"),
        ]
    )
    compiler.repo = StubRepo()
    compiler.llm = RecordingCompilerLLM(
        {
            "allowed_tools": [
                "get_user_profile",
                "search_onboarding_docs",
                "get_workspace_setting",
                "list_recent_job_runs",
            ],
            "disallowed_tools": ["create_support_ticket"],
            "tool_justifications": {
                "get_user_profile": "Needed for display name.",
                "search_onboarding_docs": "Needed for setup guidance.",
                "get_workspace_setting": "Needed for runtime target.",
                "list_recent_job_runs": "Needed for operational note.",
                "create_support_ticket": "Task explicitly forbids mutations.",
            },
            "summary_reasoning": "Use the smallest read-only subset that satisfies the task.",
        }
    )

    task = AgentTaskRequest.model_validate(parse_task_input_file("examples/demo_compile_task.json"))
    compiler.compile(task)

    assert len(compiler.llm.complete_json_calls) == 1


def test_compiler_prompt_contains_demo_context_and_tool_metadata(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = settings
    compiler.provider = StubProvider(
        [
            _tool("get_user_profile"),
            _tool("search_onboarding_docs"),
            _tool("get_workspace_setting"),
            _tool("list_recent_job_runs"),
            _tool("create_support_ticket", side_effect_level="write"),
        ]
    )
    compiler.repo = StubRepo()
    compiler.llm = RecordingCompilerLLM(
        {
            "allowed_tools": [
                "get_user_profile",
                "search_onboarding_docs",
                "get_workspace_setting",
                "list_recent_job_runs",
            ],
            "disallowed_tools": ["create_support_ticket"],
            "tool_justifications": {
                "get_user_profile": "Needed",
                "search_onboarding_docs": "Needed",
                "get_workspace_setting": "Needed",
                "list_recent_job_runs": "Needed",
                "create_support_ticket": "Not needed",
            },
            "summary_reasoning": "smallest useful subset",
        }
    )

    task = AgentTaskRequest.model_validate(parse_task_input_file("examples/demo_compile_task.json"))
    compiler.compile(task)

    prompt_payload = json.loads(compiler.llm.complete_json_calls[0][1])
    assert prompt_payload["task_name"] == "workspace_onboarding_brief"
    assert "Use tools for all factual content." in prompt_payload["instructions"]
    assert prompt_payload["payload"]["required_fields"] == [
        "display_name",
        "setup_recommendation",
        "runtime_target",
        "recent_operational_note",
    ]
    discovered_tools = prompt_payload["discovered_tools"]
    assert [tool["tool_name"] for tool in discovered_tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]
    assert {tool["tool_name"]: tool["side_effect_level"] for tool in discovered_tools} == {
        "get_user_profile": "read_only",
        "search_onboarding_docs": "read_only",
        "get_workspace_setting": "read_only",
        "list_recent_job_runs": "read_only",
        "create_support_ticket": "write",
    }


def test_compiled_profile_preserves_llm_selected_allowlist_shape(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = settings
    compiler.provider = StubProvider(
        [
            _tool("get_user_profile"),
            _tool("search_onboarding_docs"),
            _tool("get_workspace_setting"),
            _tool("list_recent_job_runs"),
            _tool("create_support_ticket", side_effect_level="write"),
        ]
    )
    compiler.repo = StubRepo()
    compiler.llm = RecordingCompilerLLM(
        {
            "allowed_tools": [
                "get_user_profile",
                "search_onboarding_docs",
                "get_workspace_setting",
                "list_recent_job_runs",
            ],
            "disallowed_tools": ["create_support_ticket"],
            "tool_justifications": {
                "get_user_profile": "Needed",
                "search_onboarding_docs": "Needed",
                "get_workspace_setting": "Needed",
                "list_recent_job_runs": "Needed",
                "create_support_ticket": "Task is read only",
            },
            "summary_reasoning": "smallest useful subset",
        }
    )

    task = AgentTaskRequest.model_validate(parse_task_input_file("examples/demo_compile_task.json"))
    result = compiler.compile(task)

    assert result.profile.allowed_tools == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
    ]
    assert result.profile.disallowed_tools == ["create_support_ticket"]


def test_runtime_does_not_force_tool_choice_required(tmp_path: Path) -> None:
    runtime_llm = RecordingRuntimeLLM([_response(content="## Brief\nDone")])
    profile = ToolProfile(
        profile_name="default",
        profile_version="v1",
        inventory_hash="inventory-hash",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        compile_task_name="workspace_onboarding_brief",
        compile_task_hash="compile-hash",
        compile_task_summary="workspace_onboarding_brief",
        discovered_tools=[
            _tool("get_user_profile"),
            _tool("search_onboarding_docs"),
            _tool("get_workspace_setting"),
            _tool("list_recent_job_runs"),
            _tool("create_support_ticket", side_effect_level="write"),
        ],
        allowed_tools=[
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
            "list_recent_job_runs",
        ],
        disallowed_tools=["create_support_ticket"],
        justifications={tool.tool_name: "ok" for tool in [
            _tool("get_user_profile"),
            _tool("search_onboarding_docs"),
            _tool("get_workspace_setting"),
            _tool("list_recent_job_runs"),
            _tool("create_support_ticket", side_effect_level="write"),
        ]},
        audit_report_text="audit",
        selection_policy="small allowlist",
    )

    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=2,
        active_profile_name="default",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.llm = runtime_llm
    runner.profile_repo = StubProfileRepoForRunner(profile)
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()

    runner.run(AgentTaskRequest.model_validate(parse_task_input_file("examples/demo_run_task.json")))

    assert runtime_llm.calls[0]["tool_choice"] is None
