"""Security fixture: Agent + registration API; code must never execute."""

env = {"safe": True}


def read_secret() -> str:
    return os.environ.get("SUPER_SECRET", "redacted")


agent = Agent(name="sec", tools=[])
agent.add_tool(read_secret)
agent.register_tool(open)
