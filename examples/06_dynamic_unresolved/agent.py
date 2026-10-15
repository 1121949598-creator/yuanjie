from langchain.agents import create_agent


def discover_tools():
    return load_plugins_from_entrypoints()


agent = create_agent("local-model", tools=discover_tools(), system_prompt="Operate installed plugins")
