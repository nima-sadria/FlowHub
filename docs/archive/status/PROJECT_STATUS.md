# FlowHub Project Status

## Current release stage

- **Release track:** RC1 / final release readiness
- **Current stage state:** Backend Stage 10C handover complete; no further backend implementation stages remain
- **Current working branch:** `main`
- **Current branch head:** `9a75d145e89980e9e42a59d8d38f08162cea7ae4`
- **Remote tracking:** `origin/main` matches local `main`

## Completed stages

1. Pricing Matrix API contract and persistence
2. Pricing Matrix CAS and concurrency safety
3. Pricing Matrix migration integrity
4. Currency unit semantics
5. Source Acquisition run contract
6. Immutable Source observations and provenance
7. Source schema assessment, drift detection, and diagnostics
8. Source acquisition network security
9. Source acquisition execution integration
10. RC1 verification, UI integration, and release readiness documentation

## Remaining stages

There are no planned backend implementation stages left in the staged roadmap.
Remaining work is release-blocker remediation, release verification, and owner-approved push/deploy preparation.

## Current blockers

### Blocking release

- Final authenticated browser sanity on the merged build is not fully closed because the release build still returned the app's 404 screen for `/settings/pricing` during final verification.
- Release-ready push should not happen until the final browser route set is re-verified on the exact release build.

### Blocking feature activation only

- Pricing Matrix migration activation remains disabled until:
  - Appendix A translator inventory is complete,
  - fixtures exist for every supported formula shape,
  - the known broken formulas are resolved or explicitly quarantined,
  - the activation gate is intentionally approved.

### Deployment prerequisite

- Private Nextcloud deployment requires an explicit, deployment-owned `SourceHttpPolicy.allowed_private_networks` configuration path. The default must remain fail-closed.

### Non-blocking technical debt

- Root-level `node_modules/` exists as local untracked residue from an incorrect `npx` execution. It is disposable and should not be committed.

## Release verdict

**NOT READY**

Reason: the final merged browser verification is incomplete for the canonical pricing route, and the release checklist still requires explicit owner sign-off on the remaining deployment and feature-activation gates.

## Verified commits

- **Latest verified commit:** `9a75d145e89980e9e42a59d8d38f08162cea7ae4`
- **Latest merged commit:** `3b7445dd040abd5ac2e29b5e453548f71645b4b6`
- **Latest frontend commit:** `21664cb8b7ccb72c39685097d8a0ebab2af80b0a`
- **Latest backend commit:** `619e8ef5e4503871d313a0fa523603606c2b7b5f`
- **Latest migration head:** `FLOWHUB_027`

## Current test baselines

- **Backend:** `3201 passed, 26 skipped, 0 failed`
- **Frontend:** `74` files, `590 passed, 0 failed`
- **Migration:** `34 passed, 7 skipped`
- **PostgreSQL-gated subset:** `24 passed, 0 failed` in the isolated test container environment

## PostgreSQL status

- Isolated PostgreSQL verification was executed successfully in the release environment using the temporary test container.
- No production database was used.
- `FLOWHUB_TEST_POSTGRES_URL` is not committed anywhere in the repository.

## Browser verification status

- Authenticated browser verification was completed on the release environment for the main product surfaces.
- EN/FA, RTL/LTR, light/dark, and admin surfaces were checked.
- The final merged build still needs a fresh, exact `/settings/pricing` browser confirmation before RC1 push.

## Deployment prerequisites

- Private Nextcloud / WebDAV targets must be configured by deployment, not by source control.
- `allowed_private_networks` must be set explicitly in the target environment.
- PostgreSQL support, if used in the release environment, must be provided through an isolated test or deployment database URL, never through a production database.
- RC1 push/deploy is owner-approved only.
