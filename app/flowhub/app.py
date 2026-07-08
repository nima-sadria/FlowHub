"""FlowHub FastAPI application entry point.

Deployment: uvicorn app.flowhub.app:app --host 0.0.0.0 --port 8085

Active routes:
  GET  /api/health                             - public health probe
  POST /api/auth/login                         - issue JWT access + refresh tokens
  POST /api/auth/logout                        - revoke refresh token
  POST /api/auth/refresh                       - rotate refresh token
  GET  /api/auth/me                            - current user profile
  GET  /api/v2/setup/status                    - public setup completion check
  POST /api/v2/setup/server-profile            - wizard step 1
  POST /api/v2/setup/database                  - wizard step 2
  POST /api/v2/setup/admin                     - wizard step 3
  POST /api/v2/setup/complete                  - lock wizard
  GET  /api/v2/products                        - paginated product browser
  GET  /api/v2/products/categories             - product category list
  GET  /api/v2/sources                         - configured data sources
  GET  /api/v2/workspace/state                 - workspace state
  POST /api/v2/workspace/preview               - compute preview (stateless)
  POST /api/v2/write-pipeline/dry-run          - create approved-safety preview for WooCommerce price update
  POST /api/v2/write-pipeline/batches/{id}/approve - approve a dry run without executing
  POST /api/v2/write-pipeline/batches/{id}/execute - apply approved WooCommerce price update
  GET  /api/v2/settings                        - read runtime settings
  POST /api/v2/settings                        - update non-credential settings
  POST /api/v2/settings/woocommerce            - replace connector credentials
  POST /api/v2/settings/nextcloud              - replace connector credentials
  GET  /api/v2/commerce/sources                - Commerce Hub source catalog
  GET  /api/v2/commerce/channels               - Commerce Hub channel catalog
  GET  /api/v2/activity                        - paginated audit log
  GET  /api/v2/diagnostics/status              - live system diagnostics
  POST /api/v2/diagnostics/run                 - run read-only diagnostics
  GET  /api/v2/diagnostics/history             - diagnostics history
  GET  /api/v2/data-layer/status               - Data Layer overall status
  GET  /api/v2/data-layer/products/status      - product cache status
  GET  /api/v2/data-layer/sources/status       - snapshot status
  GET  /api/v2/data-layer/connectors/status    - connector health + telemetry
  GET  /api/v2/data-layer/refresh-jobs         - refresh job history
  GET  /api/v2/data-layer/invalidation-events  - invalidation event log
  GET  /                                       - SPA entry point
  *    /{any}                                  - SPA fallback
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.flowhub.api.health import router as health_router
from app.flowhub.auth.router import router as auth_router
from app.flowhub.api.v2.setup import router as setup_router
from app.flowhub.api.v2.config import router as config_router
from app.flowhub.api.v2.products import router as products_router
from app.flowhub.api.v2.sources import router as sources_router
from app.flowhub.api.v2.workspace import router as workspace_router
from app.flowhub.api.v2.write_pipeline import router as write_pipeline_router
from app.flowhub.api.v2.settings_routes import router as settings_router
from app.flowhub.api.v2.commerce import router as commerce_router
from app.flowhub.api.v2.activity import router as activity_router
from app.flowhub.api.v2.diagnostics import router as diagnostics_router
from app.flowhub.api.v2.data_layer_routes import router as data_layer_router
from app.flowhub.api.v2.integrations import router as integrations_router
from app.flowhub.api.v2.integration_platform import router as integration_platform_router
from app.flowhub.api.v2.logging import router as logging_router

_VERSION = os.getenv("FLOWHUB_VERSION", "1.0.0")

_FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
_STATIC_LOGOS = Path(__file__).parent.parent.parent / "static" / "logos"
_STATIC_FONTS = Path(__file__).parent.parent.parent / "static" / "fonts"

_FRONTEND_UNAVAILABLE_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FlowHub</title>
  <link rel="icon" type="image/x-icon" href="/static/logos/favicon.ico?v=2">
  <style>
    @font-face {{
      font-family: 'YekanBakh';
      src: url('/static/fonts/YekanBakh-VF.woff2') format('woff2'),
           url('/static/fonts/YekanBakh-VF.woff') format('woff');
      font-weight: 100 900;
      font-style: normal;
      font-display: swap;
    }}
    body {{ font-family: 'YekanBakh', monospace; max-width: 600px; margin: 60px auto; padding: 0 20px; color: #222; }}
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

# API routers - registered before the SPA catch-all so they take priority
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(setup_router, prefix="/api/v2")
app.include_router(integrations_router, prefix="/api/v2")
app.include_router(integration_platform_router, prefix="/api/v2")
app.include_router(logging_router, prefix="/api/v2")
app.include_router(products_router, prefix="/api/v2")
app.include_router(sources_router, prefix="/api/v2")
app.include_router(workspace_router, prefix="/api/v2")
app.include_router(write_pipeline_router, prefix="/api/v2")
app.include_router(settings_router, prefix="/api/v2")
app.include_router(commerce_router, prefix="/api/v2")
app.include_router(config_router, prefix="/api/v2")
app.include_router(activity_router, prefix="/api/v2")
app.include_router(diagnostics_router, prefix="/api/v2")
app.include_router(data_layer_router, prefix="/api/v2")

# Static assets (hashed filenames produced by Vite; only mounted if built)
_assets_dir = _FRONTEND_DIST / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

if _STATIC_LOGOS.exists():
    app.mount("/static/logos", StaticFiles(directory=str(_STATIC_LOGOS)), name="static-logos")

if _STATIC_FONTS.exists():
    app.mount("/static/fonts", StaticFiles(directory=str(_STATIC_FONTS)), name="static-fonts")


@app.get("/", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def root() -> HTMLResponse | FileResponse:
    """Serve the React SPA at the public root."""
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse(content=_FRONTEND_UNAVAILABLE_HTML.format(version=_VERSION))


@app.get("/{full_path:path}", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def spa(full_path: str) -> HTMLResponse | FileResponse:
    """Serve the React SPA for all non-API routes, or the landing page if not built."""
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse(content=_FRONTEND_UNAVAILABLE_HTML.format(version=_VERSION))
