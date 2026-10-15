from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .agent_security.demo import DemoFeatureUnavailable, require_feature
from .engine import ScanEngine
from .repair import RepairService
from .reporting import write_report


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings(demo_mode=args.demo)
    if args.data_dir:
        settings.data_dir = Path(args.data_dir).resolve()
    return settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yuanjian", description="源界 static security auditor")
    parser.add_argument("--data-dir", help="Local state directory (default: .yuanjian-data)")
    parser.add_argument("--demo", action="store_true", help="Demo mode: disable repair, preview and rescan")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan"); scan.add_argument("path"); scan.add_argument("--model")
    report = sub.add_parser("report"); report.add_argument("scan_id"); report.add_argument("--output")
    repair = sub.add_parser("repair"); repair.add_argument("scan_id")
    rescan = sub.add_parser("rescan"); rescan.add_argument("scan_id")
    train = sub.add_parser("train"); train.add_argument("dataset"); train.add_argument("--output", required=True); train.add_argument("--seed", type=int, default=42)
    evaluation = sub.add_parser("evaluate"); evaluation.add_argument("config")
    serve = sub.add_parser("serve"); serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _settings(args)
    try:
        require_feature(settings, args.command)
    except DemoFeatureUnavailable as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.command == "scan":
        if args.model:
            import joblib

            model = joblib.load(args.model)
        else:
            model = None
        result = ScanEngine(settings, model_bundle=model).scan(args.path)
        print(json.dumps({"scan_id": result.id, "summary": result.to_dict()["summary"]}, ensure_ascii=False, indent=2))
    elif args.command == "report":
        engine = ScanEngine(settings); result = engine.store.get(args.scan_id)
        output = Path(args.output) if args.output else settings.scans_dir / args.scan_id / "report.html"
        print(write_report(result, output.resolve()))
    elif args.command == "repair":
        engine = ScanEngine(settings)
        print(RepairService(settings, engine.secret_scanner).create_safe_copy(engine.store.get(args.scan_id)))
    elif args.command == "rescan":
        engine = ScanEngine(settings); previous = engine.store.get(args.scan_id)
        if not previous.safe_copy_path:
            RepairService(settings, engine.secret_scanner).create_safe_copy(previous); previous = engine.store.get(args.scan_id)
        result = engine.scan(previous.safe_copy_path, parent_scan_id=previous.id)
        print(json.dumps({"scan_id": result.id, "comparison": result.comparison}, ensure_ascii=False, indent=2))
    elif args.command == "train":
        from .ml import train_model

        print(json.dumps(train_model(Path(args.dataset), Path(args.output), args.seed), ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        from .ml import evaluate

        print(json.dumps(evaluate(Path(args.config)), ensure_ascii=False, indent=2))
    elif args.command == "serve":
        import uvicorn
        from .web import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
