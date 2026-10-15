"""Fixture K: CrewAI-style multi-Agent isolation with BaseTool class Tools."""
from crewai import Agent
from crewai.tools import BaseTool


class ReadTool(BaseTool):
    name: str = "read_note"
    description: str = "Read a note file"

    def _run(self, path: str) -> str:
        return open(path, encoding="utf-8").read()


class ShellTool(BaseTool):
    name: str = "shell"
    description: str = "Run an admin shell command"

    def _run(self, command: str) -> str:
        return subprocess.run(command, shell=True, check=True).stdout


reader = Agent(
    role="Reader",
    goal="Read notes safely",
    tools=[ReadTool()],
)

admin = Agent(
    role="Admin",
    goal="Administer the system",
    tools=[ShellTool()],
)
