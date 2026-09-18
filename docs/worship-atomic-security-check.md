# Atomic Privilege Boundary Check

2026-09-19. Disposable PostgreSQL 17.6 only. No production SQL, grants, data
changes, backup or activation were performed by this check.

The private prototype is now exercised behind four SECURITY DEFINER wrappers
owned by a dedicated NOLOGIN, NOSUPERUSER, NOBYPASSRLS role. Its fixed search_path
is `pg_catalog, pg_temp`; application relations/functions are schema-qualified.
Anonymous collaborative editing is retained intentionally, not authenticated
writer identity. The fixture is not a production migration.

Verified using non-administrator session authorization, not merely SET ROLE from
a superuser connection:

- anon can create, read, save and delete through the intended RPCs;
- authenticated can save/replay; stale revisions reject without changing data;
- both roles retain SELECT for presenter reads, but direct INSERT/UPDATE/DELETE
  on all four aggregate tables is denied;
- private helpers, receipts and adopting the writer role are denied;
- PUBLIC does not inherit wrapper execution; an unrelated role cannot call it;
- referenced song/version validation works with the required FOR SHARE privilege;
- temporary unqualified relations cannot shadow the schema-qualified reads;
- an injected receipt failure rolls back metadata, document and checkpoint even
  when invoked through the definer wrapper;
- deletion retains a private recovery checkpoint.

Run:

```sh
WORSHIP_TEST_ENGINE=postgres WORSHIP_TEST_PG_VERSION=17.6 PGLITE_ROOT=/private/tmp/mindex-atomic-deps node tests/test_worship_atomic_security.mjs
```

## Still Blocking Activation

This does not validate production policies, role membership, other definer
functions or canonical FK cascades. The fixture starts from known synthetic
tables, rather than removing unknown live policies. Canonical mutation revision
handling, usable draft/conflict recovery, a tested restoration operation,
receipt/checkpoint retention and live capacity checks remain required.

Before any production cutover: refresh the live catalog audit, verify and restore
a backup in isolation, review the migration against that catalog, verify active
editing/output sessions, then perform a coordinated compatible-client rollout.
Never turn on the protocol flag or revoke existing DML based only on this test.
