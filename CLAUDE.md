# FlowHub — Runtime Debug Policy

Applies to every UI change made in this repo.

## Selectors
- Never use a translated/localized string as a CSS selector or test selector (e.g. `[aria-label="Source options"]`). aria-label text changes per locale and the rule silently stops matching.
- Use a stable semantic class, `data-*` attribute, or id instead. Keep `aria-label` on the element for accessibility, translated as normal — it just isn't the styling/test hook.

## The browser is the source of truth
Editing a source file is not the change taking effect. A UI task is not complete until all of the following are true, checked in the actual running browser — not inferred from the diff:
- The running dev server (backend + Vite) is serving the exact commit being edited, and hot reload (or a manual refresh) has actually picked up the edit.
- Playwright has navigated to the affected page and the change is visible in a fresh snapshot/screenshot — not assumed from a previous verification.
- Browser console is clean (no new errors/warnings vs. baseline).
- Network tab is clean (no new failed/unexpected requests).
- The change would survive a plain page refresh, i.e. it isn't an artifact of stale client state — reload and re-check before calling it done.

Keep the dev servers and the Playwright browser session running across the whole debugging session rather than restarting per-change — restart automatically only if one drops.

## Verification before calling a UI change done
Run the app and verify with Browser MCP (Playwright) rather than reasoning from code alone. Scale the checklist to what the change actually touches — don't run axes that can't be affected by the diff (e.g. a copy-only rename doesn't need a tablet/mobile viewport sweep or permission-role checks if it isn't gated).

Always check when relevant to the change:
- **Locale**: English and Persian (`en`, `fa`) — verify translated strings render as expected.
- **Direction**: LTR and RTL layout.
- **Theme**: light and dark.
- **Viewport**: desktop; add tablet/mobile if the change touches layout/responsive CSS.
- **Data states**: empty, loading, error, success — if the component has these states.
- **Interaction states**: disabled, hover, focus — if present on the changed element.
- **Permissions**: read-only / editor / admin — only if the change touches a permission-gated path.
- **Accessibility**: keyboard navigation, focus order, aria attributes.
- **Browser console**: no new errors/warnings introduced.
- **Network**: no new failed/unexpected requests.
- Related pages/components that share the changed code (search for other usages before declaring done).

State explicitly which of the above were actually checked for a given change — don't claim a blanket sweep that wasn't run.

## Workflow
1. Implement the change.
2. Run the app, verify visually with Browser MCP.
3. Check console + network.
4. Check related/affected pages.
5. Add regression tests covering the fix.
6. Commit.
7. Push `audit/integration-20260728` to `origin` after commits are ready — **not** to `main` directly. This branch tracks `origin/main`; a bare `git push` would fast-forward `main`, so push explicitly to the named branch, or confirm the target before pushing if that ever changes.
