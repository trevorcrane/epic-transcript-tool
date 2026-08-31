from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_epic_call_iq_design_tokens_are_present():
    html = HTML.read_text()
    assert "--color-purple: #7b2ff7" in html
    assert "--color-pink: #f107a3" in html
    assert "linear-gradient(115deg, #7b2ff7 0%, #c22ffc 48%, #f107a3 100%)" in html
    assert "Avenir Next" in html
    assert "surface-light" in html


def test_primary_control_stays_first_viewport_and_functional_ids_remain():
    html = HTML.read_text()
    assert "hero-control" in html
    assert html.index('id="url"') < html.index('id="result"')
    for required_id in ["form", "url", "grab", "file", "drop", "result", "transcript", "copyBtn", "downloadBtn", "downloadMdBtn", "downloadSrtBtn"]:
        assert f'id="{required_id}"' in html


def test_design_has_dark_presentation_and_light_results_surfaces():
    html = HTML.read_text()
    assert "dark-stage" in html
    assert "light-stage" in html
    assert "radial-gradient(circle, rgba(123, 47, 247, 0.18)" in html
    assert "#f7f6f3" in html
