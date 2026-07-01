"""FlowHub FastAPI application entry point.

Deployment: uvicorn app.beta.app:app --host 0.0.0.0 --port 8085

Active routes:
  GET  /api/health                             â€” public health probe
  POST /api/auth/login                         â€” issue JWT access + refresh tokens
  POST /api/auth/logout                        â€” revoke refresh token
  POST /api/auth/refresh                       â€” rotate refresh token
  GET  /api/auth/me                            â€” current user profile
  GET  /api/v2/setup/status                    â€” public setup completion check
  POST /api/v2/setup/server-profile            â€” wizard step 1
  POST /api/v2/setup/database                  â€” wizard step 2
  POST /api/v2/setup/admin                     â€” wizard step 3
  POST /api/v2/setup/complete                  â€” lock wizard
  GET  /api/v2/products                        â€” paginated WC product browser  (BU5)
  GET  /api/v2/products/categories             â€” WC category list              (BU5)
  GET  /api/v2/sources                         â€” configured data sources       (BU5)
  GET  /api/v2/workspace/state                 â€” workspace state               (BU5)
  POST /api/v2/workspace/preview               â€” compute preview (stateless)   (BU5)
  GET  /api/v2/settings                        â€” read runtime settings         (BU5)
  POST /api/v2/settings                        â€” update non-credential settings(BU5)
  POST /api/v2/settings/woocommerce            â€” replace WC credentials        (BU5)
  POST /api/v2/settings/nextcloud              â€” replace NC credentials        (BU5)
  GET  /api/v2/activity                        â€” paginated audit log           (BU5)
  GET  /api/v2/diagnostics/status              â€” live system diagnostics       (BU5)
  POST /api/v2/diagnostics/run                 â€” stub (B6)
  GET  /api/v2/diagnostics/history             â€” stub (B6)
  GET  /api/v2/data-layer/status               â€” Data Layer overall status     (DL1)
  GET  /api/v2/data-layer/products/status      â€” product cache status          (DL1)
  GET  /api/v2/data-layer/sources/status       â€” snapshot status               (DL1)
  GET  /api/v2/data-layer/connectors/status    â€” connector health + telemetry  (DL1)
  GET  /api/v2/data-layer/refresh-jobs         â€” refresh job history           (DL1)
  GET  /api/v2/data-layer/invalidation-events  â€” invalidation event log        (DL1)
  GET  /                                       â€” landing page
  *    /{any}                                  â€” SPA fallback
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.beta.api.health import router as health_router
from app.beta.auth.router import router as auth_router
from app.beta.api.v2.setup import router as setup_router
from app.beta.api.v2.config import router as config_router
from app.beta.api.v2.products import router as products_router
from app.beta.api.v2.sources import router as sources_router
from app.beta.api.v2.workspace import router as workspace_router
from app.beta.api.v2.settings_routes import router as settings_router
from app.beta.api.v2.activity import router as activity_router
from app.beta.api.v2.diagnostics import router as diagnostics_router
from app.beta.api.v2.data_layer_routes import router as data_layer_router
from app.beta.api.v2.integrations import router as integrations_router
from app.beta.api.v2.integration_platform import router as integration_platform_router
from app.beta.api.v2.logging import router as logging_router

_VERSION = os.getenv("FLOWHUB_VERSION", "1.0.0")

_FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

_LANDING_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FlowHub</title>
  <style>
    body {{ font-family: monospace; max-width: 600px; margin: 60px auto; padding: 0 20px; color: #222; }}
    h1 {{ font-size: 1.4rem; margin-bottom: 0.2em; }}
    table {{ border-collapse: collapse; margin-top: 1em; width: 100%; }}
    td {{ padding: 6px 12px; border: 1px solid #ddd; }}
    td:first-child {{ font-weight: bold; white-space: nowrap; }}
    .note {{ margin-top: 1.5em; padding: 10px 14px; background: #fff8e1; border-left: 3px solid #f0a500; font-size: 0.9rem; }}
    a {{ color: #1a6ebd; }}
  </style>
</head>
<body>
  <h1>FlowHub</h1>
  <table>
    <tr><td>health endpoint</td><td><a href="/api/health">/api/health</a></td></tr>
    <tr><td>status</td><td>running</td></tr>
  </table>
  <div class="note">
    Frontend assets are not available. Run <code>npm run build</code> inside <code>frontend/</code>
    then restart the server to activate the full UI.
  </div>
</body>
</html>
"""

app = FastAPI(
    title="FlowHub",
    version=_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# API routers â€” registered before the SPA catch-all so they take priority
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(setup_router, prefix="/api/v2")
app.include_router(integrations_router, prefix="/api/v2")
app.include_router(integration_platform_router, prefix="/api/v2")
app.include_router(logging_router, prefix="/api/v2")
app.include_router(products_router, prefix="/api/v2")
app.include_router(sources_router, prefix="/api/v2")
app.include_router(workspace_router, prefix="/api/v2")
app.include_router(settings_router, prefix="/api/v2")
app.include_router(config_router, prefix="/api/v2")
app.include_router(activity_router, prefix="/api/v2")
app.include_router(diagnostics_router, prefix="/api/v2")
app.include_router(data_layer_router, prefix="/api/v2")

# Static assets (hashed filenames produced by Vite; only mounted if built)
_assets_dir = _FRONTEND_DIST / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    """Landing page â€” always served at root; shows version, environment, health endpoint."""
    return HTMLResponse(content=_LANDING_HTML.format(version=_VERSION))


@app.get("/{full_path:path}", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def spa(full_path: str) -> HTMLResponse | FileResponse:
    """Serve the React SPA for all non-API routes, or the landing page if not built."""
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse(content=_LANDING_HTML.format(version=_VERSION))
