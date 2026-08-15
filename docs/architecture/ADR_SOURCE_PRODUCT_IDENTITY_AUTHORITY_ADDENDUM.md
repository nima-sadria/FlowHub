# ADR-SOURCE-001-A2: Product Identity Authority and Local Mapping Validation

**Status:** Accepted
**Date:** 2026-08-15
**Decider:** FlowHub Owner
**Amends:** `ADR_SOURCE_ARCHITECTURE_V2.md`
**Related:** `SOURCE_ACQUISITION_DESIGN.md`, `SOURCE_CENTRIC_PRICING_WORKSPACE.md`

## Context

`ADR-SOURCE-001` already requires immutable Source Observations and forbids
Mapping, normalization, validation, and Workspace business logic from issuing
provider requests. The current Source configuration contract does not make two
consequences of that decision explicit:

1. the semantic owner of a Source Product Key is distinct from both the key
   value and every Channel Listing identifier; and
2. saving configuration is not permission to acquire a workbook or consume a
   provider-read allowance.

Without an explicit authority model, a website or marketplace identifier can
appear to be the universal FlowHub identity even though another business may
use an ERP code, accounting code, internal SKU, or another Source-owned stable
identifier. Without a separate validation lifecycle, a Mapping save can be
coupled to a hidden remote Preview and fail because the acquisition allowance
is exhausted.

## Decision

FlowHub adopts three independent product-identity concepts:

| Concept | Meaning | Scope |
| --- | --- | --- |
| **Source Product Key** | Required, nonblank, stable value by which one Source recognizes the same product across Observations and Workspace Snapshots. | One Source identity namespace. |
| **Identity Authority** | Provider-neutral metadata naming the business or external system that owns the meaning of the Source Product Key. It is not another key value. | One immutable Source Mapping revision. |
| **Channel Product Identifier** | Identifier used to resolve one Source product to one Listing in a specific Channel. | One Channel Mapping and Listing. |

The same Source column may provide the Source Product Key and any number of
Channel Product Identifiers. Different Channels may instead use different
columns. Column reuse across these semantic roles is valid and must not be
rejected by a generic one-column-one-role rule.

### Identity Authority

Identity Authority is an extensible value object, not a provider-specific
database column or a foreign key to an enabled Channel. Its minimum persisted
shape is:

```text
type: external_system | internal | custom | unspecified
system_identifier: bounded provider-neutral identifier or null
display_label: bounded optional operator label or null
```

Examples include `external_system/woocommerce`,
`external_system/snappshop`, `external_system/erp`,
`external_system/accounting`, `internal/sku`, and an Owner-defined `custom`
system. Adding a future provider or business system does not require a new
provider-specific column.

New Mapping revisions require an explicit Authority selection. Historical
Mapping revisions are represented as `unspecified`; migration never guesses an
authority from a column header, Source connector, enabled Channel, or matching
Channel identifier.

Selecting an Authority:

- does not enable or configure a Channel;
- does not create a Listing or Channel Mapping;
- does not require Channel credentials;
- does not grant provider read or write authority; and
- does not change the connector-owned meaning of a Channel Product Identifier.

### Source Product Key and Canonical Product binding

Source Product Key remains provider-neutral. The key is normalized by a pinned,
versioned identity-normalization algorithm and is unique among participating
rows within its Source identity namespace. Duplicate or blank keys block
identity validation; duplicate product names remain valid.

Successful identity validation and product resolution create or confirm a
durable Source-scoped binding:

```text
(source_id, normalization_version, hash(normalized_source_product_key))
    -> canonical_product_id
```

The binding is versioned or append-safe and is not stored in
`CanonicalProduct.sku`. A later Observation may confirm the same binding, but
cannot silently bind the same Source key to another Canonical Product. An
intentional key-authority or namespace change requires explicit Mapping review,
new validation evidence, and a separately authorized conflict-safe
reconciliation workflow; it never rewrites historical Snapshots. FLOWHUB_036
does not expose a rebind command: until that future workflow exists, a binding
conflict stays BLOCKED and must be resolved by correcting the Mapping or
Listing identity. The system never silently rebinds.

Channel matching remains independent:

```text
(channel_id, channel_product_identifier) -> listing_id -> canonical_product_id
```

Validation confirms that all resolved Listings grouped under one Source
Product Key agree with its Canonical Product binding. Draft, Review, and Apply
continue to pin Canonical Product, Listing, Channel, Mapping, cache, and
observation identities. Provider writes use the persisted Listing identifier,
not Identity Authority or Source Product Key.

### Configuration persistence and identity readiness

Saving Source, worksheet, Channel, Value Handling, or Monetary Policy
configuration is local configuration persistence. These actions perform:

```text
provider requests = 0
acquisition reservations = 0
worksheet-discovery reservations = 0
```

They may reject malformed or structurally incomplete configuration, including
a missing Identity Authority or Source Product Key mapping. They do not reject
an otherwise valid Mapping merely because no current row dataset is available
or a provider-read allowance is exhausted.

Identity readiness is a derived projection over an immutable Mapping revision
and immutable local Source evidence:

| State | Meaning | Readiness effect |
| --- | --- | --- |
| `PENDING` | No compatible local dataset exists, or existing evidence is stale for the current identity fingerprint. | Mapping is saved; Source cannot become Ready or create a new decision from that Mapping. |
| `PASS` | The complete participating dataset has nonblank, unique Source Product Keys and all binding checks pass. | Identity gate is satisfied for the exact evidence cohort. |
| `BLOCKED` | Missing keys, duplicate keys, or Source-key/CanonicalProduct binding conflicts were found. | Mapping remains saved; activation and new decision creation are blocked. |

Mapping revisions remain immutable. PASS, BLOCKED, and PENDING are not mutable
flags on a Mapping row; they are projections from append-safe validation
evidence. A configuration save may therefore produce a Saved Mapping whose
identity status is PENDING without weakening the gate for Workspace creation,
Review, or Apply.

### Local identity validation

Identity validation consumes an immutable, complete local dataset produced by
an explicit acquisition or a committed managed Sheet revision. It never calls
a provider. The dataset must retain every participating row needed to prove
missing and duplicate keys, including rows that cannot resolve to a Listing;
a candidate-only Workspace Snapshot is not sufficient.

Each validation record is bound to at least:

- Source and logical Resource Binding identities. For Nextcloud, the retained
  non-secret binding fingerprint covers normalized endpoint, account, workbook
  path, and connector identity; credentials are never fingerprint material;
- immutable Source Observation or committed Sheet Revision identity and
  checksum;
- Mapping revision identity;
- an identity fingerprint containing participating worksheets, start rows,
  Source Product Key references, duplicate policy, and algorithm versions;
- validation algorithm version;
- a binding-context fingerprint covering each relevant Listing identity,
  Mapping version, enabled/resolved state, and effective Canonical Product
  binding;
- PASS or BLOCKED outcome, counts, bounded conflict evidence, and timestamp;
  and
- any durable Source-key/CanonicalProduct binding evidence it confirmed.

The identity fingerprint excludes unrelated Channel price, stock, status,
Value Handling, Monetary Policy, and display-only Authority label changes.
Changing those values does not manufacture a need for another Source read. A
new Mapping revision with the same identity fingerprint may reuse the prior
identity result against the same immutable dataset, while recording evidence
bound to the new revision where the persistence contract requires it.
Changing the Source key reference, participating-row scope, Resource Binding,
or identity algorithm requires new compatible local validation evidence.

Workspace creation pins this exact local dataset and assessment cohort for row
resolution, validation, Snapshot provenance, and binding proposals. A durable
binding proposal is created only when the complete Listing cohort for that
Source key is present, enabled, resolved, and Canonical-Product-consistent.
Every Listing in that cohort is locked and rechecked at commit, including a
Listing that did not produce a candidate because its cache or target value was
invalid. A binding is accepted only for a Source product that produces at least
one Workspace candidate; an entirely failed product does not create identity
state as a side effect. The resulting binding identities are recorded in
Snapshot provenance. Workspace creation never selects a second "latest"
dataset and never performs acquisition implicitly.

Changing a Source's endpoint, account, workbook path, or connector binding is
serialized with Workspace creation through the same locked Source version.
Every mounted settings API either delegates to that fenced Source-settings
command or rejects the generic write. Credential-only rotation does not change
the non-secret Resource Binding and does not invalidate compatible evidence.

The immutable Source Observation owns either a retained normalized grid or an
authorized immutable artifact from which that grid can be reproduced locally.
Retention may remove raw bytes only when retained normalized rows, hashes, and
algorithm versions preserve every held validation and Workspace guarantee.

### Explicit I/O and allowance semantics

FlowHub keeps four operations distinct:

| Operation | Provider I/O | Allowance |
| --- | --- | --- |
| Save configuration | Never | None |
| Source Mapping identity validation or identity Preview | Never | None |
| Worksheet discovery or header refresh | Only through an explicit action | Separate discovery allowance |
| Read Source / acquisition / refresh business data | Only through an explicit action | Acquisition allowance |

If no compatible local dataset exists, the interface presents `PENDING` and an
explicit `Read Source` or `Create Snapshot` action. It does not disguise that
action as Save or Preview. An exhausted acquisition allowance belongs to the
explicit acquisition command and does not turn a configuration save into a
Source-read failure.

## Consequences

Positive consequences:

- FlowHub supports website, marketplace, ERP, accounting, SKU, and custom
  identity authorities without provider-specific schema growth.
- Identity Authority cannot accidentally activate Channel operations.
- Source configuration work remains possible when provider access or quota is
  unavailable.
- Identity guarantees remain fail-closed at readiness and decision boundaries.
- Validation evidence is reproducible and tied to exact immutable inputs.
- Channel identifiers remain connector-owned and independently mappable.

Costs and trade-offs:

- Authority metadata, Source-key bindings, complete normalized local datasets,
  and append-safe validation evidence require additive persistence.
- Existing latest-only validation rows are projections, not sufficient
  historical evidence.
- Mapping and Source readiness must be shown separately in API and UI.
- Retaining a complete validation dataset costs more storage than retaining
  only candidate rows or worksheet metadata.

## Compatibility and migration

Migration is additive and forward-only:

1. preserve every existing Source Product Key, Mapping revision, Listing,
   Workspace Snapshot, Draft, Review, Apply record, and audit event;
2. represent historical authority as `unspecified` and infer no provider;
3. add no provider-specific identity columns;
4. keep legacy WooCommerce compatibility prefills explicitly legacy and
   operator-confirmed;
5. preserve existing archived Source and replacement-connector behavior; and
6. bind new readiness evidence to immutable Observation and Mapping revisions
   without rewriting historical decisions.

New Mapping writes use identity policy v2 and require Identity Authority plus
Source Product Key. Policy v1 remains readable only for historical revisions;
those revisions project PENDING and must be explicitly upgraded before a new
Workspace can be created. FLOWHUB_036 backfills policy v2 only when an existing
shared Mapping has an explicit required Source Product Key, or every enabled
per-worksheet rule has one. Mixed or partial historical worksheet mappings stay
v1/PENDING. Authority remains `unspecified`; no provider is inferred, and an
unspecified historical Mapping remains PENDING until the Owner explicitly
chooses its authority.

Managed Source Workspace creation requires a persisted `source_id` and replays
that Source's local evidence. The separate legacy Workspace Preview command is
an explicit acquisition workflow and is not a Source Mapping identity Preview.

The migration does not reset Source data, Channel mappings, credentials,
quotas, or history.

## Rejected alternatives

### Treat the primary Channel identifier as Source identity

Rejected. It conflates Source truth with Channel operations and fails for
multi-provider, ERP, accounting, internal-SKU, and custom authority models.

### Infer Authority from matching column references

Rejected. The same column may legitimately serve multiple roles, and equal
values do not prove which system owns their meaning.

### Validate by silently reading the provider during Save

Rejected. It violates `ADR-SOURCE-001`, consumes an operational allowance
without explicit intent, and prevents configuration persistence when remote
data is unavailable.

### Store validation state directly on a mutable Mapping revision

Rejected. Readiness changes as Observation evidence changes; mutating the
Mapping would destroy the immutable decision input. Validation remains a
separate evidence relationship and projection.

## Implementation gates

- Backend tests prove configuration saves perform zero provider calls and zero
  acquisition or discovery reservations.
- Local validation tests cover PASS, BLOCKED, PENDING, missing keys, duplicate
  keys, duplicate names, cross-worksheet scope, and Source-key binding conflict.
- Identity examples cover WooCommerce, SnappShop, ERP/accounting, internal SKU,
  custom authority, same-column reuse, and different per-Channel identifiers.
- Browser tests prove quota exhaustion does not block Mapping persistence and
  reload retains Authority and mappings.
- Workspace creation and every new decision fail closed unless compatible PASS
  evidence exists.
- Architecture guards prevent Mapping/validation services from importing
  provider transports and prevent provider-specific Source identity columns.
- LTR, RTL, light, and dark interfaces distinguish Saved, PENDING, PASS, and
  BLOCKED without collapsing them into a generic error.

## References

- `ADR_SOURCE_ARCHITECTURE_V2.md`
- `SOURCE_ACQUISITION_DESIGN.md`
- `SOURCE_CENTRIC_PRICING_WORKSPACE.md`
- `UNIFIED_MULTI_CHANNEL_WORKSPACE.md`
