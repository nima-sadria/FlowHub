# Codex Auditor Instructions

This document defines audit expectations for Codex and other agents reviewing
FlowHub changes. FlowHub is a production application, so production-bound work
requires a Production Audit before final release acceptance.

## Repository Audit

Repository audits verify implementation quality only:

- code quality
- architecture
- tests
- documentation
- migrations
- security
- coding standards

A successful repository audit does not authorize deployment by itself.

## Production Audit

After deployment to the production server, every release must undergo a
Production Audit.

The audit target is the running production deployment, not merely the Git
repository. The audit must verify the actual deployed system, including:

- deployed Git commit
- Docker containers
- runtime configuration
- PostgreSQL database
- migrations
- frontend production build
- static assets
- reverse proxy behavior
- browser runtime
- authenticated API behavior
- production logs
- scheduled workers
- background services
- health endpoints
- real UI workflows

The audit must confirm that the deployed application behaves correctly in the
production environment.

## Required Production Verification

Every Production Audit must verify at minimum:

- deployed commit hash
- Docker Compose status
- application logs
- worker logs
- health endpoints
- authenticated browser workflows
- browser network requests
- JavaScript console
- HTTP status codes
- static asset loading
- PostgreSQL schema
- Alembic migration head
- scheduled/background workers
- notification system
- connector configuration
- diagnostics
- sidebar
- permissions
- production environment variables

## Browser Validation

Production Audit must include validation of the deployed UI.

At minimum, verify:

- Dashboard
- Products
- Orders
- Commerce Hub
- Sources
- Workspace
- Diagnostics
- Settings

For each relevant workflow, confirm:

- no HTTP 500 responses
- no JavaScript runtime errors
- no missing assets
- correct notifications
- correct icons
- correct RTL behavior
- correct Configure / Settings actions
- successful authenticated workflows

## Final Decision

For production releases:

- Repository Audit may approve code quality.
- Only Production Audit may issue the final PASS for deployment acceptance.

If Repository Audit passes but Production Audit fails, the release status remains
HOLD until Production Audit passes.
