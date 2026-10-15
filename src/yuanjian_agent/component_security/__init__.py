"""Static component fact extraction and the V1 intent/capability adapter (member B side).

Reuses the existing capability rules and source-span / stable-id helpers from
the main codebase. Produces contract-1.0 payloads consumed by member C's
``IntentCapabilityInput``.
"""
from __future__ import annotations

from .facts import (
    PARSER_VERSION,
    BoundaryFact,
    CapabilityFact,
    ComponentFacts,
    EvidenceFact,
    detect_component,
    extract_component_facts,
    mask_excerpt,
)
from .agent_resolver import (
    AgentDeclaration,
    AgentResolver,
    ToolBindingFact,
    effective_agent_facts,
    resolve_agent_declarations,
)
from .module_index import ModuleInfo, PythonModuleIndex
from .symbol_resolver import CrossModuleSymbolResolver, ResolvedTool, ToolExpansion
from .parsers import McpParser, SkillParser
from .intent_adapter import SCHEMA_VERSION, IntentCapabilityAdapter
from .contract import ContractError, IntentCapabilityInput, IntentCapabilityResult
from .v1 import EvidenceConstrainedScorer
from .integration import ComponentSecurityPipeline

__all__ = [
    "PARSER_VERSION",
    "SCHEMA_VERSION",
    "AgentDeclaration",
    "AgentResolver",
    "BoundaryFact",
    "CapabilityFact",
    "ComponentFacts",
    "CrossModuleSymbolResolver",
    "EvidenceFact",
    "IntentCapabilityAdapter",
    "ContractError",
    "IntentCapabilityInput",
    "IntentCapabilityResult",
    "EvidenceConstrainedScorer",
    "ComponentSecurityPipeline",
    "McpParser",
    "ModuleInfo",
    "PythonModuleIndex",
    "ResolvedTool",
    "SkillParser",
    "ToolBindingFact",
    "ToolExpansion",
    "detect_component",
    "effective_agent_facts",
    "extract_component_facts",
    "mask_excerpt",
    "resolve_agent_declarations",
]
