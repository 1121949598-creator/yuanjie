"""Read-only presentation endpoints and explicitly selected synthetic examples."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, JSONResponse
from .secret.schemas import compact_mask
from .secret.query import secret_type
from .secret.remediation import remediation_for

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples"
EXAMPLES = {
    "release": ("07_release_review", "开源发布前的基础检查", "检查疑似凭据、许可证及依赖；发现 Agent 结构时提示专项审查。"),
    "research": ("01_langchain_research", "研究助手的过度授权", "识别论文研究任务额外绑定的 Shell 工具。"),
    "secrets": ("02_secret_project", "代码里的敏感凭据", "检测合成 API Key 和数据库凭据，查看脱敏证据。"),
    "dynamic": ("06_dynamic_unresolved", "无法确定的动态绑定", "展示静态分析的覆盖边界与人工复核提示。"),
    "mcp": ("05_mcp_static", "MCP 工具的能力边界", "查看静态 MCP 配置及工具能力，不启动 Server。"),
}


def _example(example_id: str):
    spec = EXAMPLES.get(example_id)
    if spec is None or not (EXAMPLE_ROOT / spec[0]).is_dir():
        raise HTTPException(404, "Example not found")
    return spec, EXAMPLE_ROOT / spec[0]


def _public_report(saved):
    """Export only presentation fields; legacy Secret lines remain withheld."""
    result = saved.to_dict()

    def pick(value, keys):
        return {key: value[key] for key in keys if key in value}

    payload = pick(result, ("id", "project_name", "created_at", "status", "version", "summary"))
    payload["findings"] = []
    for finding, original in zip(result["findings"], saved.findings):
        item = pick(finding, ("id", "category", "rule_id", "severity", "confidence", "title", "review_status"))
        secret = finding["category"] == "secret"
        item["evidence"] = []
        for evidence in finding["evidence"]:
            projected = pick(evidence, ("source_span", "masked_excerpt"))
            if secret:
                projected["masked_excerpt"] = compact_mask(evidence.get("masked_excerpt"))
            else:
                projected["details"] = pick(evidence.get("details", {}), (
                    "agent_id", "tool_id", "impact", "necessity_signal", "exposure_score",
                    "model", "evidence_kind", "resolution_status", "resolution_reason",
                ))
            item["evidence"].append(projected)
        item["rationale"] = [] if secret else finding["rationale"]
        item["remediation"] = (remediation_for(secret_type(original)).steps if secret else finding["remediation"])
        payload["findings"].append(item)
    payload["agents"] = [pick(a, ("id", "framework", "name", "task_text", "source_spans", "extraction_status"))
                         for a in result["agents"]]
    payload["tools"] = [pick(t, ("id", "framework", "name", "description", "source_spans", "capabilities", "controls", "extraction_status"))
                        for t in result["tools"]]
    payload["bindings"] = result["bindings"]
    payload["metadata"] = pick(result["metadata"], (
        "scanners", "context_model", "execution_policy", "tool_rules_version", "presentation",
        "scan_profile", "component_security_scene",
    ))
    # Historical diagnostic strings can contain target-controlled source text.
    payload["warnings"] = (["保存的扫描含诊断记录，请结合各模块的状态与覆盖信息复核。"] if saved.warnings else [])
    payload["report_note"] = "静态检查结果及脱敏证据；覆盖不完整时不能据零风险断言安全。许可证完整库存请查看许可证页面。"
    return payload


def create_presentation_router(engine, settings, scan_project):
    router = APIRouter(prefix="/api", tags=["Presentation"])

    @router.get("/system")
    def system():
        return {
            "name": "源界", "version": settings.app_version,
            "mode": "demo" if settings.demo_mode else "standard",
            "authentication": "none", "execution_policy": "static-only-never-execute-target",
            "license_provider_configured": bool(settings.scanners.enable_scancode or settings.scanners.enable_ort),
            "license_provider": "ScanCode" if settings.scanners.enable_scancode else "ORT" if settings.scanners.enable_ort else None,
            "max_upload_bytes": settings.limits.max_total_bytes,
            "scoring_model": "deterministic-context-baseline", "realtime_scan_progress": False,
        }

    @router.get("/scans")
    def history(limit: int = Query(50, ge=1, le=200)):
        return {"items": [{
            "id": r.id, "project_name": r.project_name, "created_at": r.created_at,
            "status": r.status, "summary": r.to_dict()["summary"],
            "scanners": r.to_dict()["metadata"].get("scanners", {}),
            "is_example": bool(r.metadata.get("presentation", {}).get("example_id")),
            "scan_profile": r.metadata.get("scan_profile"),
            "metadata": {"component_security_scene": r.metadata.get("component_security_scene")},
        } for r in engine.store.list(limit)]}

    @router.get("/examples")
    def examples():
        return {"items": [{"id": key, "title": v[1], "description": v[2], "synthetic": True}
                          for key, v in EXAMPLES.items() if (EXAMPLE_ROOT / v[0]).is_dir()]}

    @router.get("/examples/{example_id}/archive")
    def archive(example_id: str):
        spec, root = _example(example_id)
        stream = BytesIO()
        with ZipFile(stream, "w", ZIP_DEFLATED) as target:
            for item in sorted(root.rglob("*")):
                if item.is_file() and not item.is_symlink() and "__pycache__" not in item.parts:
                    target.write(item, f"{spec[0]}/{item.relative_to(root).as_posix()}")
        return Response(stream.getvalue(), media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="yuanjian-{example_id}-synthetic.zip"'
        })

    @router.post("/examples/{example_id}/scan", status_code=201)
    def scan_example(example_id: str):
        spec, root = _example(example_id)
        profile = {"research": "agent", "dynamic": "agent", "mcp": "download"}.get(example_id, "project")
        result = scan_project(root, project_name=spec[1], profile=profile)
        result.metadata["presentation"] = {"example_id": example_id, "synthetic": True}
        engine.store.save(result)
        return {"scan_id": result.id, "status": result.status}

    @router.get("/scans/{scan_id}/report")
    def report(scan_id: str):
        try:
            result = engine.store.get(scan_id)
        except KeyError:
            raise HTTPException(404, "Scan not found") from None
        return JSONResponse(_public_report(result), headers={"Content-Disposition": 'attachment; filename="yuanjian-risk-report.json"'})

    return router
