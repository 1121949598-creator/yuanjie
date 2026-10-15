from pathlib import Path
from crewai import Agent
from crewai.tools import BaseTool


class DeleteAnythingTool(BaseTool):
    name: str = "delete_any_file"
    description: str = "Delete any path supplied by the agent"

    def _run(self, path: str) -> str:
        Path(path).unlink()
        return "deleted"


assistant = Agent(role="Documentation helper", goal="Answer questions about project documentation", tools=[DeleteAnythingTool()])
