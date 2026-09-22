from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def config() -> tuple[str, str]:
    values = {
        key.strip(): value.strip().strip("\"'")
        for path in (ROOT / ".env.supabase.local", ROOT / ".env.supabase")
        if path.exists()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
        for key, value in (line.split("=", 1),)
    }
    url = os.environ.get("SUPABASE_URL") or values.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY") or values.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("Supabase URL and anon key are required.")
    return url.rstrip("/"), key


def request(url: str, key: str, path: str, payload: dict | None = None):
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    data = None
    method = "GET"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
        method = "POST"
    with urlopen(Request(f"{url}/rest/v1/{path}", headers=headers, data=data, method=method), timeout=30) as response:
        return json.load(response)


def main() -> int:
    url, key = config()
    services = request(url, key, "mindex_worship_services?select=id,save_revision&limit=1")
    if not services:
        print("SKIP no worship service is available for a read-only RPC check")
        return 0
    expected = services[0]
    try:
        aggregate = request(url, key, "rpc/get_worship_service_v1", {"sid": expected["id"]})
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"FAIL atomic read RPC: HTTP {error.code} {body[:500]}")
        return 1
    actual = aggregate.get("service", {})
    if actual.get("id") != expected["id"] or aggregate.get("revision") != str(expected["save_revision"]):
        print("FAIL atomic aggregate identity or revision mismatch")
        return 1
    print(json.dumps({
        "status": "PASS",
        "serviceId": actual["id"],
        "revision": aggregate["revision"],
        "sections": len(aggregate.get("sections", [])),
        "elements": len(aggregate.get("elements", [])),
        "slides": len(aggregate.get("slides", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
