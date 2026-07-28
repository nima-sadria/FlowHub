# Local Browser Debugging

FlowHub has an isolated local development runtime for UI debugging. It uses a
local SQLite database and generated credentials under `.local/`; it never reads
Production configuration or provider credentials.

## Prerequisites

- Python 3.12
- Node.js 20 or newer, with npm
- Google Chrome, or a Playwright-supported Chromium installation
- VS Code for the one-command launch workflow

## Prepare

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/prepare.ps1
```

The preparation command:

- creates `.venv` and installs Python requirements when missing;
- installs frontend packages when missing;
- migrates `.local/dev/flowhub.db`;
- creates a generated local Owner account;
- writes the credentials to `.local/dev/credentials.json`;
- writes the local Claude Code MCP configuration to `.mcp.json`.

All generated files are ignored by Git. Do not copy local credentials into
source files, VS Code settings, screenshots, traces, or bug reports.

## One-command VS Code launch

Open Run and Debug, choose `FlowHub: Full Stack + Browser`, and press `F5`.
VS Code starts the backend on `127.0.0.1:8000`, starts Vite on
`127.0.0.1:5173`, and opens an isolated Chrome debugging profile.

Stopping the debug session runs `FlowHub: stop local stack`. Logs remain under
`.local/dev/logs/` for local inspection.

The same runtime can be started outside VS Code:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local.ps1
```

Stop it with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/stop_local.ps1
```

## Claude Code browser MCP

The generated `.mcp.json` uses the official Playwright MCP package installed in
`frontend/node_modules`. Restart Claude Code after preparation so it reloads
the project MCP configuration.

The Playwright server can navigate and interact with the app, inspect
accessibility snapshots and DOM state, read console messages, and inspect
network requests. Its persistent browser profile and output are stored under
`.local/browser-profile/claude` and `.local/browser-mcp`.

The configuration calls the package with `node` directly instead of a Windows
`npx.cmd` wrapper, avoiding stdio transport issues.

## Live Playwright regression test

Run the authenticated real-backend smoke test with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/test_live.ps1
```

For interactive debugging against an already running local stack:

```powershell
cd frontend
npm run test:e2e:live:debug
```

The live test checks health, login, navigation, relevant API responses, failed
requests, and browser console errors. Screenshots, video, trace files, reports,
and test output are retained only on failure and remain ignored.
