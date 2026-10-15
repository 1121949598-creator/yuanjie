"""A synthetic CLI only: never imports or executes anything from its input root."""
import json
import os
from pathlib import Path
import sys
import time

fixture, mode, *args = sys.argv[1:]
if "--version" in args:
    if mode == "probe-timeout":
        time.sleep(20)
    print("ScanCode version: " + ("99.0.0" if mode == "unsupported-version" else "32.4.1"))
elif "--help" in args:
    print("--license --package --json --strip-root --processes --timeout --quiet" if mode != "bad-help" else "--license")
else:
    assert set(args[::1]).isdisjoint({"--license-text", "--copyright", "--email", "--url", "--config-file"})
    assert args[:2] == ["--license", "--package"]
    assert args[args.index("--processes") + 1] == "-1"
    assert Path.cwd() != Path(args[-1])
    assert os.environ.get("HOME") == str(Path.cwd())
    assert not any(k in os.environ for k in ("PYTHONPATH", "PYTHONHOME", "AWS_SECRET_ACCESS_KEY", "HTTP_PROXY", "SCANCODE_OPTIONS"))
    path = Path(args[args.index("--json") + 1])
    assert path.parent == Path.cwd()
    if mode == "timeout":
        time.sleep(20)
    if mode == "invalid-json":
        path.write_text("{invalid RAW-UPSTREAM-TEXT-DO-NOT-PERSIST", encoding="utf-8")
    elif mode == "oversize":
        path.write_text("x" * 200_000, encoding="utf-8")
    elif mode == "no-output":
        pass
    else:
        data = json.loads(Path(fixture).read_text(encoding="utf-8"))
        if mode == "partial":
            data["files"][0]["scan_errors"] = ["RAW-UPSTREAM-TEXT-DO-NOT-PERSIST"]
        if mode == "header-mismatch":
            data["headers"][0]["tool_version"] = "32.9.9"
        path.write_text(json.dumps(data), encoding="utf-8")
    if mode == "stderr-limit":
        sys.stderr.write("x" * 300_000)
    elif mode == "stdout-limit":
        sys.stdout.write("x" * 300_000)
    else:
        sys.stderr.write("RAW-UPSTREAM-TEXT-DO-NOT-PERSIST")
    if mode == "nonzero":
        sys.exit(2)
    if mode == "partial-exit":
        sys.exit(1)
