# Contributing

Thanks for helping improve FlowHub.

## Development

1. Fork or branch from `main`.
2. Keep changes scoped to one purpose.
3. Run backend tests, frontend build/tests, and `git diff --check`.
4. Open a pull request with a clear summary and verification notes.

## Safety Rules

- Do not enable write execution without Owner approval.
- Do not add Apply, Scheduler execution, or pricing automation in a polish change.
- Keep connector capability metadata separate from authorization.
- Mask secrets in responses, logs, docs, and screenshots.

## Local Checks

```bash
python -m pytest tests/flowhub -q
npm run build
npm test -- --run
git diff --check
```
