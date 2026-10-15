from __future__ import annotations

import base64
import binascii
import hmac
import uuid
from threading import Lock
from zipfile import BadZipFile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .agent_security.demo import DemoFeatureUnavailable, feature_metadata, require_feature
from .engine import ScanEngine
from .license.router import create_license_router
from .repair import RepairService
from .secret.router import create_secret_router
from .presentation import create_presentation_router
from .safe_import import UnsafeProjectError
from .scan_profiles import resolve_profile


PACKAGE_DIR = Path(__file__).parent
SHARE_USERNAME = "yuanjian"


def _shared_preview_authorized(header: str, password: str) -> bool:
    if len(header) > 4096 or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True)
    except (binascii.Error, ValueError):
        return False
    username, separator, supplied_password = decoded.partition(b":")
    return bool(separator) and hmac.compare_digest(username, SHARE_USERNAME.encode()) and hmac.compare_digest(
        supplied_password, password.encode()
    )


def create_app(settings: Settings | None = None, *, share_password: str | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = ScanEngine(settings)
    repair = RepairService(settings, engine.secret_scanner)
    app = FastAPI(title="源界", version=settings.app_version)
    scan_lock = Lock()

    if share_password:
        @app.middleware("http")
        async def shared_preview_auth(request: Request, call_next):
            if not _shared_preview_authorized(request.headers.get("authorization", ""), share_password):
                return PlainTextResponse(
                    "Authentication required",
                    status_code=401,
                    headers={
                        "WWW-Authenticate": 'Basic realm="yuanjian team preview", charset="UTF-8"',
                        "Cache-Control": "no-store",
                    },
                )
            return await call_next(request)

    def scan_project(path, **kwargs):
        # The shared scanner contains per-run diagnostics. Serialize scans while
        # keeping query endpoints responsive through the thread pool.
        with scan_lock:
            return engine.scan(path, **kwargs)

    @app.exception_handler(DemoFeatureUnavailable)
    async def demo_feature_unavailable(request: Request, error: DemoFeatureUnavailable):
        return JSONResponse(status_code=409, content={"detail": {
            "code": "demo_feature_disabled",
            "feature": error.feature,
            "message": str(error),
        }})

    def result_payload(result):
        payload = result.to_dict()
        # Current serving policy wins over settings recorded by an older scan.
        module = payload["metadata"].setdefault("module_data", {}).setdefault("agent_security", {})
        module.update(feature_metadata(settings))
        plan = payload["metadata"].get("scan_profile")
        if plan and "agent_security" not in plan["executed_modules"]:
            # Host capability is not evidence that this saved scan ran it.
            state = payload["metadata"]["scanners"]["agent_security"]["status"]
            for feature in ("agent_discovery", "tool_discovery", "binding_analysis", "risk_analysis"):
                module["features"][feature] = state
        return payload

    app.include_router(create_secret_router(engine.store))
    app.include_router(create_license_router(engine.store))
    app.include_router(create_presentation_router(engine, settings, scan_project))
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(request, "index.html", {"scans": engine.store.list()})

    async def save_and_scan(
        file: UploadFile,
        scene: Literal["install_precheck", "release_precheck"] | None = None,
        profile: Literal["download", "project", "agent"] | None = None,
    ):
        try:
            _, scene = resolve_profile(profile, scene)
        except ValueError:
            raise HTTPException(422, "检查场景与入口方案不匹配。") from None
        if not file.filename or Path(file.filename).suffix.lower() != ".zip":
            raise HTTPException(400, "Only ZIP uploads are accepted")
        target = settings.uploads_dir / f"{uuid.uuid4().hex}.zip"
        total = 0
        too_large = False
        with target.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.limits.max_total_bytes:
                    too_large = True
                    break
                destination.write(chunk)
        if too_large:
            target.unlink(missing_ok=True)
            raise HTTPException(413, "Upload exceeds configured size limit")
        try:
            try:
                filename = file.filename.replace("\\", "/").split("/")[-1]
                display_name = Path(filename).stem[:160] or "上传项目"
                result = await run_in_threadpool(
                    scan_project, target, project_name=display_name, scene=scene, profile=profile
                )
            except (BadZipFile, UnsafeProjectError):
                raise HTTPException(400, "ZIP 无法安全导入，请检查文件完整性、路径和大小限制。") from None
            return result
        finally:
            target.unlink(missing_ok=True)

    @app.post("/scans")
    async def upload_scan(
        file: UploadFile = File(...),
        scene: Literal["install_precheck", "release_precheck"] | None = Form(None),
        profile: Literal["download", "project", "agent"] | None = Form(None),
    ):
        result = await save_and_scan(file, scene, profile)
        return RedirectResponse(f"/scans/{result.id}", status_code=303)

    @app.get("/scans/{scan_id}", response_class=HTMLResponse)
    def scan_detail(request: Request, scan_id: str):
        return templates.TemplateResponse(request, "scan.html", {
            "scan": _get(engine, scan_id), "demo_mode": settings.demo_mode,
        })

    @app.get("/scans/{scan_id}/licenses", response_class=HTMLResponse)
    def license_overview_page(request: Request, scan_id: str):
        result = _get(engine, scan_id)
        return templates.TemplateResponse(
            request, "license_overview.html", {"scan_id": result.id, "project_name": result.project_name},
        )

    @app.get("/scans/{scan_id}/licenses/{assessment_id}", response_class=HTMLResponse)
    def license_detail_page(request: Request, scan_id: str, assessment_id: str):
        result = _get(engine, scan_id)
        return templates.TemplateResponse(
            request, "license_detail.html",
            {"scan_id": result.id, "assessment_id": assessment_id, "project_name": result.project_name},
        )

    @app.get("/findings/{finding_id}", response_class=HTMLResponse)
    def finding_detail(request: Request, finding_id: str, scan_id: str):
        result = _get(engine, scan_id)
        finding = next((item for item in result.findings if item.id == finding_id), None)
        if finding is None:
            raise HTTPException(404, "Finding not found")
        return templates.TemplateResponse(request, "finding.html", {"scan": result, "finding": finding})

    @app.post("/scans/{scan_id}/repair")
    def create_repair(scan_id: str):
        require_feature(settings, "repair")
        result = _get(engine, scan_id)
        if not result.safe_copy_path:
            repair.create_safe_copy(result)
        return RedirectResponse(f"/scans/{scan_id}/repair", status_code=303)

    @app.get("/scans/{scan_id}/repair", response_class=HTMLResponse)
    def repair_page(request: Request, scan_id: str):
        require_feature(settings, "repair_preview")
        result = _get(engine, scan_id)
        return templates.TemplateResponse(request, "repair.html", {"scan": result, "preview": repair.preview(result)})

    @app.post("/scans/{scan_id}/rescan")
    def rescan(scan_id: str):
        require_feature(settings, "rescan")
        result = _get(engine, scan_id)
        if not result.safe_copy_path:
            repair.create_safe_copy(result)
            result = _get(engine, scan_id)
        compared = scan_project(
            result.safe_copy_path,
            parent_scan_id=result.id,
            scene=result.metadata.get("component_security_scene", "release_precheck"),
            profile=result.metadata.get("scan_profile", {}).get("id"),
        )
        return RedirectResponse(f"/scans/{compared.id}/comparison", status_code=303)

    @app.get("/scans/{scan_id}/comparison", response_class=HTMLResponse)
    def comparison(request: Request, scan_id: str):
        require_feature(settings, "rescan")
        return templates.TemplateResponse(request, "comparison.html", {"scan": _get(engine, scan_id)})

    @app.post("/api/scans", status_code=201)
    async def api_create_scan(
        file: UploadFile = File(...),
        scene: Literal["install_precheck", "release_precheck"] | None = Form(None),
        profile: Literal["download", "project", "agent"] | None = Form(None),
    ):
        result = await save_and_scan(file, scene, profile)
        return {"scan_id": result.id, "status": result.status}

    @app.get("/api/scans/{scan_id}")
    def api_scan(scan_id: str):
        return result_payload(_get(engine, scan_id))

    @app.get("/api/scans/{scan_id}/findings")
    def api_findings(scan_id: str):
        result = _get(engine, scan_id)
        return {"scan_id": scan_id, "findings": result.to_dict()["findings"]}

    @app.get("/api/scans/{scan_id}/agent-security")
    def api_agent_security(scan_id: str):
        result = _get(engine, scan_id)
        payload = result_payload(result)
        agent_categories = {"agent_security", "tool_exposure", "unresolved"}
        return {
            "scan_id": scan_id,
            "status": result.metadata.get("scanners", {}).get("agent_security", {}),
            "module_data": payload["metadata"]["module_data"]["agent_security"],
            "rules_version": result.metadata.get("tool_rules_version", "unknown"),
            "scoring_model": result.metadata.get("context_model", "unknown"),
            "execution_policy": result.metadata.get("execution_policy"),
            "agents": payload["agents"],
            "tools": payload["tools"],
            "bindings": payload["bindings"],
            "findings": [item for item in payload["findings"] if item["category"] in agent_categories],
            "warnings": payload["warnings"],
        }

    @app.get("/api/scans/{scan_id}/component-security")
    def api_component_security(scan_id: str):
        result = _get(engine, scan_id)
        payload = result_payload(result)
        module = payload["metadata"].get("module_data", {}).get("component_security")
        if module is None:
            return {
                "scan_id": scan_id,
                "schema_version": "1.0",
                "scene": payload["metadata"].get(
                    "component_security_scene", "release_precheck"
                ),
                "status": "unavailable",
                "components": [],
                "summary": {
                    "components": 0,
                    "assessments": 0,
                    "inconsistent": 0,
                    "needs_review": 0,
                },
                "warnings": ["component_security_data_unavailable"],
            }
        return {"scan_id": scan_id, **module}

    @app.post("/api/findings/{finding_id}/repair-preview")
    def api_repair_preview(finding_id: str, scan_id: str):
        require_feature(settings, "repair_preview")
        result = _get(engine, scan_id)
        action = next((a for a in repair.preview(result)["actions"] if a["finding_id"] == finding_id), None)
        if action is None:
            raise HTTPException(404, "Finding not found")
        return action

    @app.post("/api/scans/{scan_id}/rescan")
    def api_rescan(scan_id: str):
        require_feature(settings, "rescan")
        result = _get(engine, scan_id)
        if not result.safe_copy_path:
            repair.create_safe_copy(result)
            result = _get(engine, scan_id)
        return scan_project(
            result.safe_copy_path,
            parent_scan_id=result.id,
            scene=result.metadata.get("component_security_scene", "release_precheck"),
            profile=result.metadata.get("scan_profile", {}).get("id"),
        ).to_dict()

    ui_dir = PACKAGE_DIR / "ui"
    if ui_dir.is_dir():
        app.mount("/app", StaticFiles(directory=str(ui_dir), html=True), name="frontend")
    return app


def _get(engine: ScanEngine, scan_id: str):
    try:
        return engine.store.get(scan_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


app = create_app()
