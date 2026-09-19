from __future__ import annotations

import re
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
INDEX_HTML = APP_DIR / "index.html"
APP_JS = APP_DIR / "app.js"
DESIGN_TOKENS_JS = APP_DIR / "mindex.design-tokens.js"
PRESENTER_JS = APP_DIR / "mindex.presenter.js"
STYLES_CSS = APP_DIR / "styles.css"

# Stable 2026-08-19 baseline. These are ratchets, not target architecture sizes.
# Lower a limit when code is extracted; do not raise one without documenting why.
# Raised by 6 on 2026-08-19 for the design-token bridge in app.js.
# Lower this after the next UI extraction moves literals out of app.js.
MAX_APP_JS_LINES = 27_268
MAX_PRESENTER_JS_LINES = 4_259
MAX_STYLES_LINES = 7_629
MAX_FUNCTION_LINES = 450
MAX_APP_FUNCTION_COUNT = 1_472
MAX_PRESENTER_FUNCTION_COUNT = 251
MAX_GLOBAL_COUPLING_MARKERS = 2_519

WATCHED_FUNCTION_LIMITS = {
    "handleDetailClick": 440,
    "bindStaticEvents": 345,
    "presenterElementSlideFromMemo": 200,
    "initPresenterOutput": 190,
    "buildPresenterSlidesForServiceItem": 208,
    "saveSongVersions": 140,
    "renderServiceDetail": 145,
}

GLOBAL_COUPLING_PATTERN = re.compile(
    r"\b(?:state|refs|client)\.|localStorage|BroadcastChannel|supabase|Supabase"
)
FUNCTION_PATTERN = re.compile(r"^(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(")


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def find_functions(lines: list[str]) -> list[dict[str, int | str]]:
    functions: list[dict[str, int | str]] = []
    for index, line in enumerate(lines):
        match = FUNCTION_PATTERN.match(line)
        if not match:
            continue
        depth = 0
        started = False
        end = index
        for cursor in range(index, len(lines)):
            for char in lines[cursor]:
                if char == "{":
                    depth += 1
                    started = True
                elif char == "}":
                    depth -= 1
            if started and depth <= 0:
                end = cursor
                break
        functions.append(
            {
                "name": match.group(1),
                "start": index + 1,
                "end": end + 1,
                "size": end - index + 1,
            }
        )
    return functions


def count_matches(pattern: re.Pattern[str], lines: list[str]) -> int:
    return sum(len(pattern.findall(line)) for line in lines)


def duplicate_function_names(functions: list[dict[str, int | str]]) -> list[str]:
    names = [str(function["name"]) for function in functions]
    return sorted({name for name in names if names.count(name) > 1})


def main() -> int:
    failures: list[str] = []
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_lines = read_lines(APP_JS)
    presenter_lines = read_lines(PRESENTER_JS)
    style_lines = read_lines(STYLES_CSS)
    app_functions = find_functions(app_lines)
    presenter_functions = find_functions(presenter_lines)
    by_name = {str(function["name"]): function for function in app_functions}
    largest = sorted(app_functions, key=lambda function: int(function["size"]), reverse=True)[:12]
    global_coupling = count_matches(GLOBAL_COUPLING_PATTERN, app_lines)

    if len(app_lines) > MAX_APP_JS_LINES:
        failures.append(f"app.js lines {len(app_lines)} > {MAX_APP_JS_LINES}")
    if len(presenter_lines) > MAX_PRESENTER_JS_LINES:
        failures.append(
            f"mindex.presenter.js lines {len(presenter_lines)} > {MAX_PRESENTER_JS_LINES}"
        )
    if len(style_lines) > MAX_STYLES_LINES:
        failures.append(f"styles.css lines {len(style_lines)} > {MAX_STYLES_LINES}")
    if len(app_functions) > MAX_APP_FUNCTION_COUNT:
        failures.append(
            f"app.js function count {len(app_functions)} > {MAX_APP_FUNCTION_COUNT}"
        )
    if len(presenter_functions) > MAX_PRESENTER_FUNCTION_COUNT:
        failures.append(
            "mindex.presenter.js function count "
            f"{len(presenter_functions)} > {MAX_PRESENTER_FUNCTION_COUNT}"
        )
    if global_coupling > MAX_GLOBAL_COUPLING_MARKERS:
        failures.append(f"global coupling markers {global_coupling} > {MAX_GLOBAL_COUPLING_MARKERS}")

    for label, file_functions in (
        ("app.js", app_functions),
        ("mindex.presenter.js", presenter_functions),
    ):
        duplicates = duplicate_function_names(file_functions)
        if duplicates:
            failures.append(f"duplicate top-level functions in {label}: {', '.join(duplicates)}")

    cross_file_duplicates = sorted(
        {str(function["name"]) for function in app_functions}
        & {str(function["name"]) for function in presenter_functions}
    )
    if cross_file_duplicates:
        failures.append(
            "top-level function ownership collision between app.js and "
            f"mindex.presenter.js: {', '.join(cross_file_duplicates)}"
        )

    script_positions = [
        index_html.find("mindex.constants.js"),
        index_html.find("mindex.design-tokens.js"),
        index_html.find("mindex.presenter.js"),
        index_html.find("app.js"),
    ]
    if any(position < 0 for position in script_positions) or script_positions != sorted(script_positions):
        failures.append(
            "runtime script order must be mindex.constants.js, "
            "mindex.design-tokens.js, mindex.presenter.js, app.js"
        )

    for function in largest:
        if int(function["size"]) > MAX_FUNCTION_LINES:
            failures.append(
                f"{function['name']} length {function['size']} > {MAX_FUNCTION_LINES} "
                f"({function['start']}-{function['end']})"
            )

    for name, limit in WATCHED_FUNCTION_LIMITS.items():
        function = by_name.get(name)
        if not function:
            failures.append(f"watched function missing: {name}")
            continue
        if int(function["size"]) > limit:
            failures.append(
                f"{name} length {function['size']} > watched limit {limit} "
                f"({function['start']}-{function['end']})"
            )

    print("SOLID audit summary")
    print(f"- app.js lines: {len(app_lines)} / {MAX_APP_JS_LINES}")
    print(
        f"- mindex.presenter.js lines: {len(presenter_lines)} / {MAX_PRESENTER_JS_LINES}"
    )
    print(f"- styles.css lines: {len(style_lines)} / {MAX_STYLES_LINES}")
    print(f"- app.js function count: {len(app_functions)} / {MAX_APP_FUNCTION_COUNT}")
    print(
        "- mindex.presenter.js function count: "
        f"{len(presenter_functions)} / {MAX_PRESENTER_FUNCTION_COUNT}"
    )
    print(f"- global coupling markers: {global_coupling} / {MAX_GLOBAL_COUPLING_MARKERS}")
    print(f"- cross-file function collisions: {len(cross_file_duplicates)}")
    print("- largest functions:")
    for function in largest:
        print(
            f"  {function['size']:>4} lines  {function['name']} "
            f"({function['start']}-{function['end']})"
        )

    if failures:
        print("FAIL solid-audit")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS solid-audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
