from mcp.server.fastmcp import FastMCP


server = FastMCP("notes")


@server.tool()
def read_note(name: str) -> str:
    """Read a note from the allowed notes directory."""
    path = (NOTES_ROOT / name).resolve()
    if not path.is_relative_to(NOTES_ROOT):
        raise ValueError("outside allowlist")
    return path.read_text(encoding="utf-8")
