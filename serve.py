#!/usr/bin/env python3
import html
import http.server
import json
import os
import pathlib
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = pathlib.Path(__file__).resolve().parent
ENV_PATHS = (
    ROOT / ".env.supabase.local",
    ROOT / ".env.supabase",
)


def read_env_files():
    values = {}
    for path in ENV_PATHS:
        if not path.exists():
            continue
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def local_supabase_config():
    values = {**read_env_files(), **os.environ}
    url = values.get("MINDEX_SUPABASE_URL") or values.get("SUPABASE_URL") or ""
    anon_key = (
        values.get("MINDEX_SUPABASE_ANON_KEY")
        or values.get("SUPABASE_ANON_KEY")
        or values.get("SUPABASE_PUBLIC_ANON_KEY")
        or ""
    )
    if not url or not anon_key:
        return ""
    return json.dumps({"url": url, "anonKey": anon_key})


def inject_local_config(markup):
    config = local_supabase_config()
    if not config or "window.MINDEX_SUPABASE" in markup:
        return markup
    script = f"<script>window.MINDEX_SUPABASE={html.escape(config, quote=False)};</script>"
    return markup.replace("</head>", f"    {script}\n  </head>", 1)

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        self.byte_range = None
        parts = pathlib.Path(unquote(urlsplit(self.path).path)).parts
        target = pathlib.Path(self.translate_path(self.path)).resolve()
        try:
            relative = target.relative_to(ROOT.resolve())
        except ValueError:
            self.send_error(404)
            return None
        blocked_dirs = {'docs', 'tests', 'tools', 'scripts', 'data', 'backups', 'migrations'}
        if (any(p.startswith('.') for p in (*parts, *relative.parts))
                or (relative.parts and relative.parts[0] in blocked_dirs)
                or target.suffix.lower() in {'.py', '.md', '.sql', '.log', '.sqlite', '.db', '.sh', '.toml', '.plist'}):
            self.send_error(404)
            return None
        requested = self.headers.get("Range", "")
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
        if self.command != "GET" or not match or self.headers.get("If-Range"):
            return super().send_head()
        first, last = match.groups()
        if not first and not last:
            return super().send_head()
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()
        try:
            source = open(path, "rb")
        except OSError:
            return super().send_head()
        stat = os.fstat(source.fileno())
        size = stat.st_size
        start = int(first) if first else max(0, size - int(last))
        end = min(int(last), size - 1) if first and last else size - 1
        if size == 0 or start >= size or end < start or (not first and int(last) == 0):
            source.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        source.seek(start)
        self.byte_range = (start, end)
        return source

    def list_directory(self, path):
        self.send_error(404)
        return None

    def copyfile(self, source, outputfile):
        if self.byte_range is None:
            return super().copyfile(source, outputfile)
        remaining = self.byte_range[1] - self.byte_range[0] + 1
        while remaining:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def do_GET(self):
        if self.path in ("", "/") or self.path.split("?", 1)[0] == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            markup = (ROOT / "index.html").read_text(encoding="utf-8")
            self.wfile.write(inject_local_config(markup).encode("utf-8"))
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *_):
        pass

def main():
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 2300))
    http.server.test(HandlerClass=NoCacheHandler, port=port, bind='127.0.0.1')


if __name__ == "__main__":
    main()
