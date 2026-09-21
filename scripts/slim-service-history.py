#!/usr/bin/env python3
"""Slim mindexServiceDocumentHistory entries in production (drop slides/sourceRecords/exceptions, keep counts).

Dry run by default: reads only, writes a local backup, prints what would change. Nothing is written
to the database unless --apply is given. Credentials are read from .env.supabase.local and never printed.

    python3 scripts/slim-service-history.py            # dry run + backup
    python3 scripts/slim-service-history.py --apply --limit 1   # canary: newest service only
    python3 scripts/slim-service-history.py --apply    # rewrite (compare-and-set on updated_at)
    python3 scripts/slim-service-history.py --restore backups/<file>.json   # dry run of a restore
    python3 scripts/slim-service-history.py --restore backups/<file>.json --apply
"""
import argparse, datetime, gzip, json, pathlib, sys, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
HIST = "mindexServiceDocumentHistory"
DOC = "mindexServiceDocument"
DROP = ("slides", "sourceRecords", "exceptions")


def load_env():
    env = {}
    for name in (".env.supabase.local", ".env.supabase"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env.setdefault(key, value.strip().strip("\"'"))
    url = next((v for k, v in env.items() if "URL" in k.upper() and v.startswith("http")), "")
    key = next((v for k, v in env.items() if "ANON" in k.upper() or "PUBLISHABLE" in k.upper()), "")
    if not url or not key:
        sys.exit("Supabase config not found")
    return url.rstrip("/"), key


def request(url, key, path, method="GET", body=None, headers=None):
    p, _, q = path.partition("?")
    full = f"{url}/rest/v1/{p}" + ("?" + urllib.parse.quote(q, safe="=&,()*.:%") if q else "")
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Accept-Encoding": "gzip", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(full, data=data, method=method, headers=h)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw) if raw else None


def slim_entry(entry):
    if not isinstance(entry, dict):
        return entry
    slim = {k: v for k, v in entry.items() if k not in DROP}
    for arr, count in (("sourceRecords", "sourceRecordCount"), ("slides", "slideCount")):
        if isinstance(entry.get(arr), list) and entry[arr]:
            slim[count] = len(entry[arr])
    return slim


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def write_backup(backup, backup_dir, now=None):
    out_dir = pathlib.Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S-%f")
    payload = json.dumps(backup, ensure_ascii=False)
    for suffix in range(1000):
        marker = "" if suffix == 0 else f"-{suffix}"
        path = out_dir / f"service-history-before-slim-{stamp}{marker}.json"
        try:
            with path.open("x", encoding="utf-8", errors="strict", newline="") as handle:
                handle.write(payload)
            return path
        except FileExistsError:
            continue
    raise RuntimeError("Could not create a unique service-history backup file")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups"))
    parser.add_argument("--limit", type=int, default=0, help="with --apply: rewrite only the newest N services first (canary)")
    parser.add_argument("--only", default="", help="with --apply: rewrite only services whose id starts with this prefix (canary)")
    args = parser.parse_args()
    url, key = load_env()

    if args.restore:
        backup = json.loads(pathlib.Path(args.restore).read_text())
        print(f"restore plan: {len(backup['rows'])} rows from {args.restore} ({'APPLY' if args.apply else 'dry run'})")
        for row in backup["rows"]:
            current = request(url, key, f"mindex_worship_services?select=id,updated_at,source_ref&id=eq.{row['id']}")
            if not current:
                print("  skip (row gone)", row["id"][:8]); continue
            ref = dict(current[0]["source_ref"]); ref[HIST] = row["history"]
            print(f"  {row['id'][:8]} history {size(current[0]['source_ref'].get(HIST))} -> {size(row['history'])} bytes")
            if args.apply:
                done = request(url, key, f"mindex_worship_services?id=eq.{row['id']}&updated_at=eq.{current[0]['updated_at']}", "PATCH", {"source_ref": ref}, {"Prefer": "return=representation"})
                print("    restored" if done else "    changed meanwhile, skipped")
        return

    rows = request(url, key, "mindex_worship_services?select=id,service_date,service_type_id,title,updated_at,source_ref&order=service_date.asc")
    targets = [r for r in rows if isinstance(r["source_ref"].get(HIST), list) and r["source_ref"][HIST]]
    backup = {"created": datetime.datetime.now().isoformat(timespec="seconds"),
              "rows": [{"id": r["id"], "updated_at": r["updated_at"], "history": r["source_ref"][HIST]} for r in targets]}
    backup_path = write_backup(backup, args.backup_dir)
    print(f"services total {len(rows)}, with history {len(targets)}; backup -> {backup_path} ({backup_path.stat().st_size // 1000} KB)")

    total_before = total_after = 0
    plans = []
    for r in targets:
        hist = r["source_ref"][HIST]
        slim = [slim_entry(e) for e in hist]
        # safety: restorable text and order must be untouched
        assert [e.get("sourceText") for e in hist] == [e.get("sourceText") for e in slim], r["id"]
        assert len(hist) == len(slim)
        before, after = size(hist), size(slim)
        total_before += before; total_after += after
        plans.append((r, slim, before, after))
        print(f"  {r['service_date']} {r['service_type_id']:<18} {r['id'][:8]} entries {len(hist)}  {before//1000:>4} KB -> {after//1000:>3} KB")
    print(f"total history {total_before/1e6:.2f} MB -> {total_after/1e6:.3f} MB ({100*(1-total_after/max(total_before,1)):.1f}% smaller)")

    if not args.apply:
        print("DRY RUN: nothing was written. Re-run with --apply to rewrite.")
        return
    ok = skipped = 0
    if args.only:
        plans = [plan for plan in plans if plan[0]["id"].startswith(args.only)]
        print(f"canary: only ids starting with {args.only} ({len(plans)} service(s))")
    if args.limit:
        plans = plans[-args.limit:]
        print(f"canary: only the newest {len(plans)} service(s)")
    for r, slim, _, _ in plans:
        ref = dict(r["source_ref"]); ref[HIST] = slim
        done = request(url, key, f"mindex_worship_services?id=eq.{r['id']}&updated_at=eq.{r['updated_at']}", "PATCH", {"source_ref": ref}, {"Prefer": "return=representation"})
        if done: ok += 1
        else:
            skipped += 1; print("  changed meanwhile, skipped", r["id"][:8])
    print(f"applied {ok}, skipped {skipped} (skipped rows keep their old history and are slimmed on their next save)")


if __name__ == "__main__":
    main()
