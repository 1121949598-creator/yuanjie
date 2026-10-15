"""Fixture B: two Agents in one file, each bound to a different Tool.

The file as a whole contains shell + read calls, but each Agent must only
inherit the capabilities of its own bound Tool (B must not see shell_execute,
A must not see file_read).
"""
from langchain.agents import create_agent


def read_tool(path: str) -> str:
    return open(path, encoding="utf-8").read()


def shell_tool(command: str) -> str:
    return subprocess.run(command, shell=True, check=True)


reader = create_agent(
    "local-model", tools=[read_tool], system_prompt="Read a selected file."
)

admin = create_agent(
    "local-model", tools=[shell_tool], system_prompt="Run admin shell commands."
)
