# FlowHub RC1 Release Checklist

Use this checklist before any RC1 push.

## Git and branch state

- [ ] `main` is the active branch
- [ ] `origin/main` matches the intended release head
- [ ] No merge/rebase/cherry-pick/revert/bisect is active
- [ ] No staged files remain outside the intentional release commit
- [ ] No accidental merge commits, debug commits, or environment artifacts are present
- [ ] Only the expected worktrees exist

## Documentation

- [ ] `PROJECT_STATUS.md` is current
- [ ] `ARCHITECTURE_STATE.md` reflects the actual implemented architecture
- [ ] `DEVELOPER_RESUME.md` contains the minimal continuation facts
- [ ] `NEXT_TASK.md` names exactly one immediate task
- [ ] `PROJECT_MEMORY.md` contains the full continuation memory
- [ ] `RESUME.md` remains consistent with the current state
- [ ] `UI_RESUME.md` is consistent with the integrated UI branch
- [ ] `FRONTEND_CONTRACT.md` matches the callable backend API exactly

## Test evidence

- [ ] Backend suite matches the documented baseline
- [ ] Migration suite matches the documented baseline
- [ ] Frontend suite matches the documented baseline
- [ ] Pricing Matrix backend tests pass
- [ ] Source Acquisition suites pass
- [ ] Connector regressions pass
- [ ] Workspace regressions pass
- [ ] no-direct-http policy passes
- [ ] release guards pass
- [ ] i18n validation passes or has an explicit approved waiver
- [ ] PostgreSQL-gated tests ran in an isolated test environment if PostgreSQL is part of the release scope

## Browser evidence

- [ ] Authenticated browser sanity ran on the final merged build
- [ ] `/settings/pricing` loads on the final build
- [ ] Pricing policy list/detail loads
- [ ] Policy Revision editor loads
- [ ] Product Group editor loads
- [ ] Unit editor loads
- [ ] Channel lifecycle controls load for admin
- [ ] Persian RTL and English LTR both render correctly
- [ ] Light and dark themes both render correctly
- [ ] At least one mobile viewport was checked
- [ ] No unexpected console errors occurred
- [ ] No undocumented API calls occurred

## PostgreSQL and deployment

- [ ] Isolated PostgreSQL verification is complete
- [ ] No production database was used
- [ ] Deployment-owned private-network config path exists for `SourceHttpPolicy.allowed_private_networks`
- [ ] No private CIDR is committed to source control
- [ ] Secrets remain outside the repository

## Pricing migration activation gate

- [ ] Appendix A translator inventory is complete
- [ ] Fixture set covers every supported formula shape
- [ ] Known broken formulas are resolved or explicitly quarantined
- [ ] Pricing migration activation is intentionally approved

## Push prerequisites

- [ ] Release verdict is explicitly approved by the owner
- [ ] Rollback reference is recorded
- [ ] Push instruction is explicit and current
- [ ] Deployment instruction is explicit and current
