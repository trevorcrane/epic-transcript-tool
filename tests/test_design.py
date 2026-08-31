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
    for required_id in ["form", "url", "grab", "file", "drop", "result", "transcript", "copyBtn", "downloadBtn", "downloadMdBtn", "downloadSrtBtn", "downloadVttBtn", "summaryBtn", "actionsBtn", "allAnalysisBtn", "analysisPanel", "analysisMenu", "questionInput", "askBtn", "analysisBox", "analysisCopyBtn", "analysisDownloadBtn"]:
        assert f'id="{required_id}"' in html


def test_phase3_video_intelligence_ui_is_wired_to_analysis_api():
    html = HTML.read_text()
    assert "AI Summary" in html
    assert "Action Items" in html
    assert "All Outputs" in html
    assert "Ask a question about this transcript" in html
    for label in ["Main ideas", "Chapters", "Best quotes", "Blog post", "Create 100 content assets"]:
        assert label in html
    assert "/api/analyze/" in html
    assert "/api/analyze-all/" in html
    assert "/api/analysis/" in html
    assert "Copy Analysis" in html
    assert "Video intelligence" in html


def test_design_has_dark_presentation_and_light_results_surfaces():
    html = HTML.read_text()
    assert "dark-stage" in html
    assert "light-stage" in html
    assert "radial-gradient(circle, rgba(123, 47, 247, 0.18)" in html
    assert "#f7f6f3" in html


def test_chatgpt_reference_layout_version_markers():
    html = HTML.read_text()
    assert "Free Video Transcript" in html
    assert "Machine" in html
    assert "Generator" not in html
    assert "FAST · FREE · V3" not in html
    assert "Get Transcript" in html
    assert "Get Video Transcript" not in html
    assert "Quick and simple. No catch." in html
    assert "Frequently Asked Questions (FAQ)" in html
    assert "faq-stage" in html
    assert "step-grid" in html
    assert html.index("hero-control") < html.index("How it works") < html.index("Frequently Asked Questions")


def test_upload_area_is_minimal_but_keeps_supported_extensions_in_accept_attribute():
    html = HTML.read_text()
    for ext in [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".txt", ".md", ".srt", ".vtt"]:
        assert ext in html
    assert "Click or drag audio, video, or transcript files here" not in html
    assert "MP4 · MOV · WebM" not in html
    assert "Choose file" in html


def test_reference_faqs_and_theme_toggle_are_present():
    html = HTML.read_text()
    for faq in [
        "How do I transcribe a YouTube video to text?",
        "How do I download a YouTube transcript?",
        "Is the YouTube transcript machine free?",
        "What is a YouTube video transcript?",
        "What are YouTube subtitles?",
        "What are YouTube closed captions?",
        "Why can't I download a transcript directly from YouTube?",
    ]:
        assert faq in html
    assert 'id="themeToggle"' in html
    assert 'aria-label="Switch to light mode"' in html
    assert "Switch to dark mode" in html
    assert "toggleTheme" in html
    assert "data-theme" in html
    assert "localStorage.setItem('epicTranscriptTheme', theme)" in html
    assert ">☀</button>" in html
    assert "? '☾' : '☀'" in html
    assert ">☀ Light</button>" not in html
    assert "? '☾ Dark' : '☀ Light'" not in html
    assert ".theme-toggle { min-width:44px; min-height:44px" in html
    assert "body[data-theme='light'] .hero-control" in html
    assert "body[data-theme='light'] .drop-zone" in html
    assert "body[data-theme='light'] .status" in html


def test_vtt_download_is_available_without_upload_clutter():
    html = HTML.read_text()
    assert 'id="downloadVttBtn"' in html
    assert "els.downloadVttBtn.addEventListener('click', () => downloadCurrent('vtt'))" in html
    assert "WEBVTT" in html
    assert "Browser-only fallback" not in html
    assert "WebGPU when available" not in html
    assert "WASM when WebGPU is not available" not in html


def test_visible_version_phase_status_is_removed_from_hero():
    html = HTML.read_text()
    assert 'aria-label="Version and phase status"' not in html
    assert "Bulletproof YouTube transcripts: public gate passed." not in html
    assert "Any video or audio: uploads and public media verified" not in html
    assert "Video intelligence: starter outputs live" not in html
