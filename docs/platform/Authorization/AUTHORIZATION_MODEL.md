# Authorization Model

## Principles

Authentication establishes actor identity. Authorization evaluates a named
capability for the requested operation and resource scope. UI visibility is
not an authorization boundary.

## Canonical Workspace Capabilities

| Capability | Meaning |
| --- | --- |
| `workspace.read` | Read Workspace, Source, Review, and status information |
| `workspace.create` | Create a Workspace or Source-owned Workspace resource |
| `workspace.edit` | Edit Workspace or Source configuration |
| `draft.save` | Persist Draft revisions or managed Sheet changes |
| `review.generate` | Generate Review from immutable inputs |
| `apply.execute` | Submit approved Write Pipeline work |
| `channel_cache.refresh` | Explicitly refresh Channel cache |
| `mapping.approve` | Approve Source-to-Channel identity mappings |
| `audit.read` | Read actor and operation evidence within scope |
| `workspace.admin` | Administrative Workspace operations |

Role-derived grants are the current policy source. Legacy `can_*` values are
temporary compatibility aliases and MUST NOT be used for new functionality.

## Enforcement

- Backend routes MUST enforce the exact capability or stronger documented
  administrative policy.
- Frontend routes and controls SHOULD use the same canonical capability to
  present read-only or unavailable states.
- Action-level `403` responses MUST remain local to the action; only the
  identity endpoint may invalidate the global authenticated state.
- Owner or administrative scope expansion MUST require a reason and audit
  evidence where cross-owner data is exposed.
- Maintenance mode MUST NOT silently bypass `apply.execute`; any privileged
  bypass must be explicit, narrowly scoped, and audited.

## Resource Scope

Every owner-scoped query MUST constrain records before pagination or
aggregation. Administrative cross-owner reads require a named policy, reason,
and audit event. Secrets remain inaccessible even to broad operational reads.

## Contract

`/api/auth/me` is the canonical frontend identity and capability contract. It
returns canonical permissions and temporary legacy aliases. Removing aliases
requires an Owner-approved compatibility release.
