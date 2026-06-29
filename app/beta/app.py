"""FlowHub Beta — FastAPI application entry point (BU4).

Deployment: uvicorn app.beta.app:app --host 0.0.0.0 --port 8085

Active routes:
  GET  /api/health                        — public health probe
  POST /api/auth/login                    — issue JWT access + refresh tokens
  POST /api/auth/logout                   — revoke refresh token (requires access token)
  POST /api/auth/refresh                  — rotate refresh token
  GET  /api/auth/me                       — current user profile (requires access token)
  GET  /api/v2/setup/status               — public setup completion check
  POST /api/v2/setup/server-profile       — save server profile (wizard step 1)
  POST /api/v2/setup/database             — verify DB + migration status (wizard step 2)
  POST /api/v2/setup/admin               — create first administrator (wizard step 3)
  POST /api/v2/setup/integrations/woocommerce — save + test WC (wizard step 4)
  POST /api/v2/setup/integrations/nextcloud   — save + test NC (wizard step 4)
  POST /api/v2/setup/complete             — lock wizard and finalize setup
  GET  /                                  — landing page (always; version/health info)
  *    /{any}                             — SPA fallback: serves frontend/dist/index.html
                                            (or the minimal landing page if not yet built)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.beta.api.health import router as health_router
from app.beta.auth.router import router as auth_router
from app.beta.api.v2.setup import router as setup_router

_VERSION = "0.2.0-bu4"

_FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

_LANDING_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WooPrice Beta</title>
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
  <h1>WooPrice Beta</h1>
  <table>
    <tr><td>environment</td><td>beta</td></tr>
    <tr><td>version</td><td>{version}</td></tr>
    <tr><td>health endpoint</td><td><a href="/api/health">/api/health</a></td></tr>
    <tr><td>status</td><td>running</td></tr>
  </table>
  <div class="note">
    Frontend not yet built. Run <code>npm run build</code> inside <code>frontend/</code>
    then restart the server to activate the full UI.
  </div>
</body>
</html>
"""

app = FastAPI(
    title="WooPrice Beta",
    version=_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# API routers — registered before the SPA catch-all so they take priority
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(setup_router, prefix="/api/v2")

# Static assets (hashed filenames produced by Vite; only mounted if built)
_assets_dir = _FRONTEND_DIST / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    """Landing page — always served at root; shows version, environment, health endpoint."""
    return HTMLResponse(content=_LANDING_HTML.format(version=_VERSION))


@app.get("/{full_path:path}", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def spa(full_path: str) -> HTMLResponse | FileResponse:
    """Serve the React SPA for all non-API routes, or the landing page if not built."""
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse(content=_LANDING_HTML.format(version=_VERSION))
