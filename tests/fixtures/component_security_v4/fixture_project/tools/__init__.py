"""Tool package re-exporting file and web tools as one collection."""
from .file_tools import read_file
from .web_tools import search_web

ALL_TOOLS = [read_file, search_web]
