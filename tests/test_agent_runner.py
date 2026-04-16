from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import AgentRunRecord, AgentTaskRequest, ToolResult, ToolSpec
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


class StubProvider:
    def __init__(self, tools: list[ToolSpec], inventory_hash: str = "inventory-hash") -> None:
        self.tools = tools
        self._inventory_hash = inventory_hash

    def list_tools(self) -> list[ToolSpec]:
        return list(self.tools)

    def inventory_hash(self) -> str:
        return self._inventory_hash


class StubExecutor:
    def __init__(self) -> None:
        self.calls = []

    def call_tool(self, tool_call):
        self.calls.append(tool_call)
        return ToolResult(
            tool_name=tool_call.tool_name,
            status="ok",
            content={"echo": tool_call.arguments},
            metadata={"request_id": tool_call.request_id},
        )


class StubWriter:
    def __init__(self) -> None:
        self.run_records = []
        self.output_records = []

    def write_run_record(self, record) -> None:
        self.run_records.append(record)

    def write_output_record(self, record) -> None:
        self.output_records.append(record)


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.call_args = []

    def tool_step(self, messages, tools, tool_choice=None):
        self.call_args.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _tool(name: str) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": [],
        },
        provider_type="local_python",
        provider_id="builtin_tools",
        capability_tags=["demo"],
        data_domains=["demo"],
        example_uses=["Example"],
    )


def _discovered_tools() -> list[ToolSpec]:
    return [
        _tool("get_user_profile"),
        _tool("search_onboarding_docs"),
        _tool("get_workspace_setting"),
        _tool("list_recent_job_runs"),
        _tool("create_support_ticket"),
    ]


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


def _runner(
    tmp_path: Path,
    llm,
    *,
    tools: list[ToolSpec] | None = None,
    max_agent_steps: int = 2,
) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=max_agent_steps,
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.provider = StubProvider(tools or _discovered_tools())
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = llm
    return runner


def test_agent_runner_returns_runtime_result_contract(tmp_path: Path) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1"),
                    ]
                ),
                _response(content="## Onboarding Brief\nAda Lovelace"),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert isinstance(record, AgentRunRecord)
    assert runner.llm.call_args[0]["tool_choice"] == "auto"
    assert [tool["function"]["name"] for tool in runner.llm.call_args[0]["tools"]] == [
        tool.tool_name for tool in tools
    ]
    assert record.result == {
        "final_response": "## Onboarding Brief\nAda Lovelace",
        "available_tools": [tool.tool_name for tool in tools],
        "available_tools_count": len(tools),
        "tool_calls": [
            {
                "tool_name": "get_user_profile",
                "arguments": {"user_id": "usr_ada_01"},
                "status": "ok",
                "error": None,
            }
        ],
    }
    assert [item.tool_name for item in runner.executor.calls] == ["get_user_profile"]
    assert runner.result_writer.run_records[0].result == record.result
    assert runner.result_writer.output_records[0].output_payload == record.result


def test_agent_runner_marks_max_steps_exceeded_with_runtime_result_payload(
    tmp_path: Path,
) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1"),
                    ]
                ),
            ]
        ),
        tools=tools,
        max_agent_steps=1,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert record.status == "max_steps_exceeded"
    assert record.error_message == "Maximum agent steps exceeded."
    assert record.result["available_tools"] == [tool.tool_name for tool in tools]
    assert record.result["available_tools_count"] == len(tools)
    assert record.result["tool_calls"][0]["status"] == "ok"


def test_agent_runner_returns_error_for_unknown_tool_call(tmp_path: Path) -> None:
    tools = _discovered_tools()[:-1]
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("create_support_ticket", '{"summary":"help"}')]),
                _response(content="Finished after the error."),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
        )
    )

    assert runner.executor.calls == []
    assert record.result["tool_calls"][0] == {
        "tool_name": "create_support_ticket",
        "arguments": {"summary": "help"},
        "status": "error",
        "error": "Unknown tool: create_support_ticket",
    }
    assert "blocked" not in {record.result["tool_calls"][0]["status"]}


def test_agent_runner_preserves_tool_call_order(tmp_path: Path) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1"),
                        _tool_call("search_onboarding_docs", '{"query":"local development"}', call_id="call-2"),
                    ]
                ),
                _response(content="Ordered trace."),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert [entry["tool_name"] for entry in record.result["tool_calls"]] == [
        "get_user_profile",
        "search_onboarding_docs",
    ]
