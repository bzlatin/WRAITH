"""Feature acceptance against the selected application's actual source code."""

import functools
import json
from pathlib import Path
import sys

import click
from click.testing import CliRunner
import llm
from llm.cli import cli, _approve_tool_call
from llm.plugins import pm


def partial_tools():
    def scale(a: int, b: int = 3, *, offset: int = 0, llm_tool_call=None) -> int:
        """Scale two numbers and add an offset."""
        return a * b + offset

    for function, explicit_name, expected in [
        (functools.partial(scale, 2), None, 6),
        (functools.partial(scale, a=4), "configured", 12),
        (functools.partial(functools.partial(scale, 2), offset=5), "nested", 11),
    ]:
        tool = llm.Tool.function(function, name=explicit_name)
        assert tool.name == (explicit_name or "scale")
        assert tool.description == scale.__doc__
        assert tool.input_schema["properties"]["b"]["type"] == "integer"
        assert "llm_tool_call" not in tool.input_schema["properties"]
        chain = llm.get_model("echo").chain(
            json.dumps({"tool_calls": [{"name": tool.name}]}), tools=[tool]
        )
        chain.text()
        assert int(chain._responses[-1].prompt.tool_results[0].output) == expected
    assert (
        llm.Tool.function(
            functools.partial(scale, 2), name="named", description="Override"
        ).description
        == "Override"
    )
    try:
        llm.Tool.function(functools.partial(lambda a: a, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("An unnamed lambda must remain rejected")


def tool_prefix():
    code = "def alpha(): return 1\ndef beta(): return 2\n"
    runner = CliRunner()
    for prefix, names in [("alpha", ["alpha"]), ("ALPHA", []), ("missing", [])]:
        result = runner.invoke(
            cli,
            ["tools", "list", "--functions", code, "--json", "--name-prefix", prefix],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert [tool["name"] for tool in json.loads(result.stdout)["tools"]] == names
    result = runner.invoke(
        cli,
        ["tools", "list", "--functions", code, "--name-prefix", "alpha"],
        catch_exceptions=False,
    )
    assert "alpha()" in result.stdout and "beta()" not in result.stdout

    class AlphaBox(llm.Toolbox):
        def ping(self) -> str:
            return "pong"

    class AlphaServer(llm.ServerSideTool):
        name = "alpha_server"

    class BetaServer(llm.ServerSideTool):
        name = "beta_server"

    class LocalModel(llm.Model):
        model_id = "pilot-server-list"
        supported_server_side_tools = (AlphaServer, BetaServer)

        def execute(self, *args, **kwargs):
            raise AssertionError("Listing must not execute a model")

    class Plugin:
        @llm.hookimpl
        def register_models(self, register):
            register(LocalModel())

        @llm.hookimpl
        def register_tools(self, register):
            register(AlphaBox)

    plugin = Plugin()
    pm.register(plugin, name="pilot-prefix")
    try:
        result = runner.invoke(
            cli,
            [
                "tools",
                "list",
                "--json",
                "-m",
                "pilot-server-list",
                "--name-prefix",
                "Alpha",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert [tool["name"] for tool in data["toolboxes"]] == ["AlphaBox"]
        assert [tool["name"] for tool in data["server_side_tools"]] == ["AlphaServer"]
    finally:
        pm.unregister(plugin)


def approval_json():
    arguments = {"z": {"b": 2, "a": 1}, "a": 'Zoë "QA"'}

    @click.command()
    def command():
        _approve_tool_call(None, llm.ToolCall("demo", arguments))
        click.echo("accepted")

    for answer, approved in [("y\n", True), ("n\n", False)]:
        result = CliRunner().invoke(command, input=answer)
        assert (
            json.dumps(arguments, ensure_ascii=False, indent=2, sort_keys=True)
            in result.output
        )
        assert "Tool call: demo" in result.output
        if approved:
            assert result.exit_code == 0 and "accepted" in result.stdout
        else:
            assert isinstance(result.exception, llm.CancelToolCall)


if __name__ == "__main__":
    source = Path(sys.argv[1]).resolve()
    assert Path(llm.__file__).resolve() == source / "llm/__init__.py"
    {
        "partial-tools": partial_tools,
        "tool-prefix": tool_prefix,
        "approval-json": approval_json,
    }[sys.argv[2]]()
    print(json.dumps({"passed": True}))
