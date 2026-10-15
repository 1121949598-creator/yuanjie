"""Fixture I: module b imports module a back (circular)."""
from a import x_tool

y_tool = x_tool
