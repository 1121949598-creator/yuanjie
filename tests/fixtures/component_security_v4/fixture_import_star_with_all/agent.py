"""Import-star with a static __all__: read_tool should resolve."""
from langchain.agents import create_agent
from lib import *

agent = create_agent("local-model", tools=[read_tool], system_prompt="Read a document.")
