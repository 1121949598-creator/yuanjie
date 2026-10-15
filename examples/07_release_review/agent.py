from langchain.agents import create_agent
from langchain.tools import tool


@tool
def search_papers(query: str) -> str:
    """Search public paper metadata on an approved host."""
    return requests.get("https://api.semanticscholar.org", params={"q": query}, timeout=5).text


@tool
def shell_exec(command: str) -> str:
    """Run an arbitrary local shell command."""
    return subprocess.run(command, shell=True, capture_output=True, text=True).stdout


agent = create_agent("local-model", tools=[search_papers, shell_exec], system_prompt="Search public papers and summarize abstracts.")
