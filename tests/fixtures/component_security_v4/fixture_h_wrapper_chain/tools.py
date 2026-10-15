"""Fixture H: cross-file wrapper Tool around a function from another module."""
from functions import read_document
from langchain.tools import StructuredTool

read_tool = StructuredTool.from_function(read_document)
