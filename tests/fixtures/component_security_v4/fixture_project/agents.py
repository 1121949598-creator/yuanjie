"""Main Batch 4 acceptance project: agents.py + tools package + config.py."""
from langchain.agents import create_agent
from tools import ALL_TOOLS

researcher = create_agent(
    "local-model",
    tools=ALL_TOOLS,
    system_prompt="Research local files and the web.",
)
