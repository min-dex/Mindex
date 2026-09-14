# Read-only operations panel

The Save-adjacent panel reports browser-tab sessions, not verified physical devices.
Sharing is opt-in on each browser. It reports environment, selected/output worship
identifiers, slide position, heartbeat/video state and the last 20 action categories.
Input contents, lyrics, attachments and raw error messages are not collected.

## Isolation and limits

- No monitor initialization on the presenter output route; no remote commands.
- Controller reports every 15 seconds, with one request chain in flight, a 4-second
  timeout and failure backoff up to 5 minutes. Viewer polling runs only while open.
- Reports older than 45 seconds are marked stale; background browser throttling can
  delay reports. This is sampled status, not a complete audit trail.
- Reporter sessions expire after 24 hours, viewers after 30 minutes. Expired rows
  are removed on registration/login, not by a scheduled retention job.
- Up to 100 reporter sessions and 10 viewer sessions. Reloading creates a new
  session. Names and state are self-reported and must not be treated as attestation.
- Five failed password attempts block all logins for the remainder of the global
  10-minute window. This protects the PIN endpoint but can temporarily block the
  administrator under deliberate abuse. A short PIN remains a weak password.

## Server setup

Apply `migrations/2026-09-13-readonly-monitor.sql` in the trusted Supabase SQL editor.
It creates isolated private tables and narrowly scoped RPCs, without changing
worship data or policies. Browser roles cannot read the private tables directly.

An administrator must set the password using the private `set_password(text)`
function in the trusted editor. Do not commit the actual password. Until configured,
registration and login fail closed. Changing the password revokes viewer sessions.
Remove any saved editor query containing the password after configuration.

Passwords and session tokens are not stored in client localStorage. Tokens are
held in memory; the server stores only token hashes. Closing the panel locks it.
Turning sharing off requests removal of that reporter's record. If offline, it
expires normally rather than silently claiming remote deletion succeeded.

## Panel hardening

The controller samples small state every two seconds; uploads remain every 15
seconds. Output connectivity uses the presenter's own heartbeat TTL. The displayed
slide is explicitly the controller selection, not proof of rendered output.
Invalid/stale timestamps and failed reads are not presented as verified live state.
Reporting errors and viewer errors have separate status areas; refresh can retry
reporting, and reconnection resumes reporting without changing worship state.

Device and action filters operate on the existing last-20-category report only.
Dates are shown with times; short session IDs distinguish identical device names.
This is still sampled operational history, not a durable audit log. No new data
fields, retention period, public permissions or database migration are introduced.

Viewer access locks when the document becomes hidden, after five minutes without
panel interaction, or after its 30-minute session lifetime. Locking clears the
password input and cached rows, aborts pending viewer requests, and revokes the
viewer token when reachable. Network/server errors never expose raw error text.
These changes do not strengthen a weak administrator password; configure a strong
password separately in the trusted server editor.

## Verification

Run `tests/smoke_monitor.py`, `tests/smoke_monitor_isolation.py`, existing presenter
latency/video tests and service-save safety tests. SQL permission and validation
tests use `tests/test_monitor_sql.mjs` with PGLite installed outside the repository.
Production cross-session verification is a separate step after password setup.
