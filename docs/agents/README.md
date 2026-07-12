# Agent Instructions

This directory contains operating instructions for agents working on FlowHub.
All Markdown files in this directory are intended to be readable by every agent
that works in the repository. They are not private notes for a single tool.

Agents should start with this README, then read the task-specific files in this
directory that match the work being performed.

Before any release, audit, deployment, production remediation, or production
verification task, agents must read:

- [Codex Auditor Instructions](CODEX_AUDITOR.md)

The Codex Auditor Instructions are mandatory for production-bound work. Repository
audits verify implementation quality only; final production acceptance requires
a Production Audit against the running deployment.

Other files in this directory are task-specific prompts or historical agent
notes. They remain readable context for any agent. When instructions conflict,
the Codex Auditor Instructions control release acceptance for production
deployments.
