import ast
from pathlib import Path


PACKAGE = Path(__file__).parents[1] / "src" / "yuanjian_agent"


def test_scanner_does_not_execute_or_import_target_modules():
    forbidden_calls = {"exec", "eval", "compile", "runpy.run_path", "subprocess.run", "subprocess.Popen", "os.system"}
    allowed_files = {"analysis.py"}
    violations = []
    for path in PACKAGE.glob("*.py"):
        if path.name in allowed_files:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            else:
                name = ""
            if name in forbidden_calls:
                violations.append(f"{path.name}:{node.lineno}:{name}")
    assert not violations, violations
