"""Import-star without __all__: symbol must not be guessed."""
from langchain.agents import create_agent
from lib2 import *

agent = create_agent("local-model", tools=[read_tool], system_prompt="Read a document.")
