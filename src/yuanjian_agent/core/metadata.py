"""A bounded JSON-only boundary for optional scanner domain data."""
import json
import math
import re


MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_METADATA_NODES = 300_000
MAX_METADATA_DEPTH = 16
MAX_METADATA_ITEMS = 20_000
MAX_METADATA_STRING = 4096
_FORBIDDEN_KEYS = {"raw", "raw_json", "raw_output", "stdout", "stderr", "env", "environment",
                   "command", "command_line", "body_source", "server_config"}


class InvalidModuleMetadata(ValueError):
    def __init__(self):
        super().__init__("Module data rejected; diagnostic details suppressed")


def safe_module_metadata(value, redactor, project_root) -> dict:
    """Copy and validate before the existing recursive final redaction runs.

    Depth is checked before descent, including cycles. No unknown objects are
    stringified. A rejected payload never discards otherwise valid findings.
    """
    if type(value) is not dict:
        raise InvalidModuleMetadata()
    nodes, size = 0, 0
    root = str(project_root)
    roots = {root, root.replace("\\", "/"), root.replace("/", "\\")}

    def visit(item, depth=0):
        nonlocal nodes, size
        nodes += 1
        if nodes > MAX_METADATA_NODES or depth > MAX_METADATA_DEPTH or size > MAX_METADATA_BYTES:
            raise InvalidModuleMetadata()
        if item is None or type(item) is bool:
            size += 5
            return item
        if type(item) is int:
            if item.bit_length() > 64:
                raise InvalidModuleMetadata()
            size += 24
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise InvalidModuleMetadata()
            size += 32
            return item
        if isinstance(item, str):
            if len(item) > MAX_METADATA_STRING:
                raise InvalidModuleMetadata()
            for prefix in roots:
                item = re.sub(re.escape(prefix), "[target root withheld]", item, flags=re.IGNORECASE)
            if re.search(r"[A-Za-z]:[\\/]|\\\\|(?:^|\s)/|[A-Za-z][A-Za-z+.-]*://", item):
                item = "[path or URL withheld]"
            item = redactor.redact_text(item)
            size += len(item.encode("utf-8")) + 2
            return item
        if type(item) not in (dict, list) or len(item) > MAX_METADATA_ITEMS:
            raise InvalidModuleMetadata()
        size += len(item) * 2 + 2
        if type(item) is list:
            return [visit(part, depth + 1) for part in item]
        output = {}
        for key, part in item.items():
            if (type(key) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
                    or key.lower() in _FORBIDDEN_KEYS):
                raise InvalidModuleMetadata()
            size += len(key) + 3
            output[key] = visit(part, depth + 1)
        return output

    output = visit(value)
    if len(json.dumps(output, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_METADATA_BYTES:
        raise InvalidModuleMetadata()
    return output
