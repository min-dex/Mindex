from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text()
RELEASE = (ROOT / "mindex-release.json").read_text()


def test_bootstrap_never_exposes_the_browser_default_canvas():
    assert '<body class="ui-booting">' in INDEX
    assert "background: #181816" in INDEX
    assert "color-scheme: dark" in INDEX
    assert "body.ui-booting .app-shell" in INDEX
    assert 'const fallbackVersion = "20260926-1830"' in INDEX
    assert '"version": "20260926-1830"' in RELEASE


if __name__ == "__main__":
    test_bootstrap_never_exposes_the_browser_default_canvas()
    print("startup bootstrap: PASS")
