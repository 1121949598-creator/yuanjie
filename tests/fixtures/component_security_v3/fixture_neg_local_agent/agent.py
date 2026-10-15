"""Negative fixture: a local class named Agent must not be treated as an AI Agent."""


class Agent:
    def __init__(self, tools=None, name=None):
        self.tools = tools or []
        self.name = name or "generic"


plain = Agent()


class AgentToolBox:
    def __init__(self):
        self.tools = []

    def add_tool(self, tool):
        self.tools.append(tool)
        return self


box = AgentToolBox()
