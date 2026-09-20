# Mindex Documentation Map

Read `HANDOFF.md` first, then open the smallest current document for the task.
When documents disagree, use the current contract or decision log and update the
stale document in the same change.

## Current Contracts

- `citation-live-output.md`: dedicated live scripture input, optional immediate
  output, draft retention, and controller scroll anchoring.

- `worship-presenter-decisions.md`: current Worship/Presenter behavior,
  service-specific rules, visual output decisions, and live-operation
  conventions.
- `worship-data-contract.md`: Supabase-backed Worship schema, persisted data
  contracts, service type IDs, input modes, and default materialization rules.
- `thread-worship-presenter.md`: implementation workflow for Worship and
  Presenter changes.
- `design-system.md`: app UI design tokens, button grammar, and design
  migration rules.
- `ui-contracts.md`: app shell and UI interaction contracts.
- `code-organization.md`: runtime script order, code ownership boundaries, and
  safe-refactoring rules.

## Planning Or Deferred Work

- `electron-packaging-plan.md`: packaging and auto-update plan.
- `admin-access-security.md`: admin and access-control planning.
- `young-adult-bulletin.md`: deferred young-adult bulletin plan. Do not expose
  bulletin UI or store arbitrary bulletin payloads until the feature is
  explicitly resumed.
- `solid-refactor-notes.md`: refactor notes only. Do not treat as a required
  migration plan unless the user asks to resume it.

## Data Review Evidence

- `handoff-worship-service-list-payload.md`: UX->Data handoff for the light service
  list read and the Data thread response (view, source_ref guard, history size).
- `design-worship-service-history-storage.md`: design only (not applied) for the size of
  `mindexServiceDocumentHistory`: slim entries first, separate table only if needed.

- `ux-audit-2026-09-18.md`: bounded UX/code/documentation audit, regression
  coverage, preserved recovery data, and unverified production boundaries.

- `hymn-reference-audit-2026-08-19.md`: read-only hymn audit and verified
  repair record. Use only as data review evidence, not as app behavior.
- `worship-slot-key-audit-2026-08-26.md`: read-only Worship slotKey adapter
  audit and migration-risk review before adding DB slot constraints.

## Retired Notes

Temporary incident logs and old worship-order drafts are not kept as active
documentation. Use Git history if you need to inspect them. Current behavior
must come from the contract documents above.

## Cleanup Rule

If a user-facing behavior changes, update the current decision log or data
contract with the same commit. Do not restore retired drafts or incident logs
as behavior sources.
