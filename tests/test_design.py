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
    for required_id in ["form", "url", "grab", "file", "drop", "browserLocal", "result", "transcript", "copyBtn", "downloadBtn", "downloadMdBtn", "downloadSrtBtn", "summaryBtn", "actionsBtn", "allAnalysisBtn", "analysisPanel", "analysisMenu", "questionInput", "askBtn", "analysisBox", "analysisCopyBtn", "analysisDownloadBtn"]:
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
    assert "FAST · FREE · V3" in html
    assert "Get Video Transcript" in html
    assert "Quick and simple. No catch." in html
    assert "Frequently Asked Questions (FAQ)" in html
    assert "faq-stage" in html
    assert "step-grid" in html
    assert html.index("hero-control") < html.index("How it works") < html.index("Frequently Asked Questions")


def test_upload_copy_lists_every_supported_format():
    html = HTML.read_text()
    for ext in [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".txt", ".md", ".srt", ".vtt"]:
        assert ext in html
    for label in ["MP4", "MOV", "WebM", "MKV", "AVI", "MP3", "M4A", "AAC", "FLAC", "OGG", "OPUS", "WAV", "TXT", "MD", "SRT", "VTT"]:
        assert label in html


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
    assert ".nav { display:flex; }" in html
    assert ".theme-toggle { min-width:44px; min-height:44px" in html


def test_browser_local_whisper_fallback_is_disclosed_and_wired():
    html = HTML.read_text()
    assert "Browser-only fallback" in html
    assert "File stays on this device" in html
    assert "WebGPU when available" in html
    assert "WASM when WebGPU is not available" in html
    assert "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2" in html
    assert "Xenova/whisper-tiny.en" in html
    assert "browser-whisper-webgpu" in html
    assert "browser-whisper-wasm" in html
    assert "canUseBrowserWhisper" in html
    assert "transcribeInBrowser" in html


def test_visible_version_phase_status_is_present():
    html = HTML.read_text()
    assert 'aria-label="Version and phase status"' in html
    assert "Version 1 / Phase 1" in html
    assert "Bulletproof YouTube transcripts" in html
    assert "Version 2 / Phase 2" in html
    assert "Any video or audio" in html
    assert "Version 3 / Phase 3" in html
    assert "Video intelligence" in html
    assert html.index("Version 1 / Phase 1") < html.index("Version 2 / Phase 2") < html.index("Version 3 / Phase 3")
