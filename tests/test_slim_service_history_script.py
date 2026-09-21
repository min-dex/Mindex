import datetime
import importlib.util
import json
import pathlib
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "slim_service_history",
    ROOT / "scripts" / "slim-service-history.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main():
    fixed = datetime.datetime(2026, 9, 21, 18, 30, 15, 123456)
    first = {"created": "first", "rows": [{"id": "one", "history": [1]}]}
    second = {"created": "second", "rows": [{"id": "two", "history": [2]}]}
    with tempfile.TemporaryDirectory() as directory:
        first_path = MODULE.write_backup(first, directory, now=fixed)
        second_path = MODULE.write_backup(second, directory, now=fixed)
        assert first_path != second_path
        assert first_path.name == "service-history-before-slim-20260921-183015-123456.json"
        assert second_path.name == "service-history-before-slim-20260921-183015-123456-1.json"
        assert json.loads(first_path.read_text(encoding="utf-8")) == first
        assert json.loads(second_path.read_text(encoding="utf-8")) == second
    print("PASS every history rewrite gets a fresh restorable backup")


if __name__ == "__main__":
    main()
