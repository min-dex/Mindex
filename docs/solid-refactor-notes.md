# SOLID Refactor Notes

This note is the lightweight guardrail for Mindex refactors. The app is still a
static HTML/CSS/JS app, so the goal is not to force a class-heavy architecture.
Use SOLID as a way to keep change boundaries small and predictable.

## Current Risk Shape

- `app.js` is the main pressure point. It contains app shell logic, data loading,
  persistence, rendering, editor events, Worship templates, Presenter controls,
  Presenter output, Praise, Scripture, Calendar, and References.
- Small visible bugs can take too long because the same change often crosses
  slide rendering, presenter output, preview thumbnails, DB fallback/loading,
  and service templates. Treat this as an operational bottleneck, not just a
  code-style concern.
- The main SOLID risk is `SRP`: several functions own event routing, state
  mutation, DOM rendering, and persistence decisions at the same time.
- `OCP` is the second risk: adding new service element types or presenter output
  behavior often means editing large conditional functions.
- `DIP` is a future risk: domain decisions are close to Supabase, localStorage,
  BroadcastChannel, and DOM APIs.
- `LSP` is not a major current concern because the app does not rely on class
  inheritance.

## Refactor Rules

- For live-service bugs, prefer a narrow hotfix first, then a minimal targeted
  smoke test. Batch broader verification after related fixes are grouped.
- Do not split files just to split files. First create small stable boundaries
  inside the current file, then move them if the boundary holds.
- Prefer registry/table-driven dispatch for action handlers and presenter
  element builders.
- Keep behavior-preserving refactors separate from feature work.
- Avoid touching broad dispatcher functions when another thread is likely editing
  `app.js`; add tests or docs first, then perform narrow extraction.
- Every important behavior refactor should add or update smoke coverage.

## Safe Sequence

1. Add guardrails and diagnostics.
2. For urgent Presenter/Worship fixes, make the smallest safe hotfix and add a
   regression smoke where possible.
3. Extract pure helpers from large functions without changing call sites.
4. Convert presenter element building to a type-to-builder map.
5. Convert detail event handling to action registries.
6. Move stable modules out of `app.js` only after their boundaries stop changing.

## Operational Speed Goal

The practical goal is faster live-service maintenance:

- Simple UI/display regressions should be fixable without reading unrelated
  Praise, Scripture, Calendar, or persistence code.
- Presenter output behavior should be isolated from controller rendering and
  authoring UI wherever possible.
- Worship service templates, slide builders, and output contexts should have
  clear boundaries so `fullscreen`, `chromakey`, `preview`, and `output` changes
  do not repeatedly touch the same large conditional blocks.
- Verification should scale with risk: hotfix + targeted smoke first, full app
  audit before commit/deploy or after a batch of related changes.

## Guardrail

Run:

```bash
python3 tests/solid_audit.py
```

The audit is intentionally conservative. It does not demand a perfect SOLID
score today. It prevents the known large functions and global coupling markers
from growing silently while Mindex is still being stabilized.
