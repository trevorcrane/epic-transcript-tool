from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_wrong_epic_call_logo_is_not_active_after_rollback():
    html = HTML.read_text()
    topbar = html[html.index('<header class="topbar">'):html.index('</header>')]
    assert 'brand-logo' not in topbar
    assert 'logo-word' not in topbar
    assert 'EPIC CALL Transcript Machine' not in topbar
    assert 'class="title">Transcript Machine</span>' in topbar
