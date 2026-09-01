from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"
BASELINE = Path(__file__).resolve().parents[1] / "static" / "versions" / "v4-before-call-iq-crawl-20260831-190857.html"


def test_v5_restores_pre_redesign_visible_copy_and_order():
    html = HTML.read_text()
    baseline = BASELINE.read_text()
    # Baseline DOM/copy/section order stays intact.
    for required in [
        "Free Video Transcript",
        "MACHINE",
        "Paste a YouTube or public media URL, or upload an audio/video/transcript file.",
        "Quick and simple. No catch.",
        "Copy the YouTube URL",
        "Paste the URL above",
        "View the YouTube transcript",
        "Unlock All EPIC Machines",
        "Frequently Asked Questions (FAQ)",
    ]:
        assert required in html
        assert required in baseline
    assert html.index('class="hero"') < html.index('id="banner"') < html.index('id="result"') < html.index("Unlock All EPIC Machines") < html.index("Frequently Asked Questions")
    for forbidden in [
        "Record. Transcribe. Download.",
        "Record. Transcribe. Repurpose.",
        "signal-shell",
        "transcript-console",
        "console-proof",
        "Transcript first. Optional AI helpers stay secondary",
        "Call IQ",
        "crawl",
        "reference",
        "design-version",
        "call-iq",
    ]:
        assert forbidden not in html


def test_v5_allows_only_color_font_version_and_functional_deltas_from_baseline():
    html = HTML.read_text()
    baseline = BASELINE.read_text()
    assert "const RELEASE_VERSION = '5.0.0'" in html
    assert "const RELEASE_VERSION = '4.0.0'" not in html
    assert "const RELEASE_VERSION = '3.2.1'" not in html
    assert 'EPIC Transcript Machine · v<span id="releaseVersion"></span> · Powered by' in html
    assert "@import url('https://fonts.googleapis.com/css2?family=Oswald" in html
    assert '--font-heading: "Oswald"' in html
    assert '--font-sans: "Inter", system-ui' in html
    assert "Avenir Next" not in html
    assert "--color-bg: #000000" in html
    assert "--color-bg-raised: #0D0D0F" in html
    assert "linear-gradient(115deg, #7b2ff7 0%, #c22ffc 48%, #f107a3 100%)" in html
    assert "--color-purple: #7b2ff7" in html
    assert "--color-pink: #f107a3" in html
    assert ".machine-band { padding:34px 20px 18px; background:#f7f6f3; color:#171719; }" in html
    assert ".machine-band h2 { font-family:var(--font-heading); color:#171719; }" in html
    assert "body[data-theme='light'] .title::before { color:rgba(23,23,25,.62); }" in html
    assert "body[data-theme='light'] .footer a { color:#7b2ff7; }" in html
    assert 'calc(100vw - 36px)' in html
    assert 'padding:16px 12px 56px' in html
    assert 'calc(100vw - 48px)' in html
    assert 'class="hero"' in html and 'class="hero-control"' in html
    assert html.index('class="hero"') < html.index('class="hero-control"')


def test_primary_control_stays_first_viewport_and_functional_ids_remain():
    html = HTML.read_text()
    assert "hero-control" in html
    assert html.index('id="url"') < html.index('id="result"')
    for required_id in ["form", "url", "grab", "file", "drop", "result", "transcript", "copyBtn", "downloadBtn", "downloadMdBtn", "downloadSrtBtn", "downloadVttBtn", "summaryBtn", "actionsBtn", "allAnalysisBtn", "analysisPanel", "analysisMenu", "questionInput", "askBtn", "analysisBox", "analysisCopyBtn", "analysisDownloadBtn"]:
        assert f'id="{required_id}"' in html


def test_phase3_video_intelligence_ui_is_wired_but_not_claimed_in_hero():
    html = HTML.read_text()
    for label in ["AI Summary", "Action Items", "All Outputs", "Ask a question about this transcript", "Main ideas", "Chapters", "Best quotes", "Blog post", "Create 100 content assets"]:
        assert label in html
    assert "/api/analyze/" in html
    assert "/api/analyze-all/" in html
    assert "/api/analysis/" in html
    hero = html[html.index('<main class="hero"'):html.index('</main>')]
    assert "Turn it into assets" not in hero
    assert "Posts and hooks" not in hero


def test_upload_history_footer_contracts_remain():
    html = HTML.read_text()
    for ext in [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".txt", ".md", ".srt", ".vtt"]:
        assert ext in html
    assert 'placeholder="Enter URL..."' in html
    assert "Enter YouTube URL" not in html
    assert 'role="button" tabindex="0" aria-label="Upload audio, video, or transcript file"' in html
    assert "els.drop.addEventListener('keydown'" in html
    assert "Your Transcript History" in html
    assert "Local to this browser" in html
    assert "No cloud sync" in html
    assert "Clear history" in html
    assert "https://epic.media" in html
    for machine in ["Content Machine", "Clip Machine", "Sales Machine", "Story Machine", "Offer Machine", "Follow-Up Machine"]:
        assert machine in html
    assert html.count("Coming Soon") >= 6


def test_v5_progress_faq_and_upload_preservation_accessibility():
    html = HTML.read_text()
    assert 'id="status" class="status" role="status" aria-live="polite" aria-atomic="true"' in html
    for faq_id in ['faq-youtube-text', 'faq-download', 'faq-free', 'faq-transcript', 'faq-subtitles', 'faq-captions', 'faq-direct-download']:
        assert f'id="{faq_id}-button"' in html
        assert f'aria-controls="{faq_id}-answer"' in html
        assert f'id="{faq_id}-answer"' in html
    assert "q.setAttribute('aria-expanded', String(isOpen));" in html
    assert "a.hidden = !isOpen;" in html
    assert 'const previousRecord = currentRecord;' in html
    assert "const previousResultVisible = els.result.classList.contains('show');" in html
    assert 'restorePreviousResult(previousRecord, previousResultVisible)' in html
    handle_file = html[html.index('async function handleFile(file) {'):html.index('function isBrowserWhisperCandidate')]
    assert "els.result.classList.remove('show')" not in handle_file


def test_browser_local_whisper_runtime_metadata_and_labels_are_truthful():
    html = HTML.read_text()
    assert "browserLocal: $('browserLocal')" in html
    assert 'function isBrowserWhisperCandidate(file)' in html
    assert 'async function transcribeInBrowser(file)' in html
    assert '@xenova/transformers' not in html
    assert 'Xenova/whisper-tiny.en' not in html
    assert 'Xenova/whisper-small' not in html
    assert '@huggingface/transformers@' in html
    assert 'onnx-community/whisper-tiny' in html
    assert 'browserWhisperDtype' in html
    assert "encoder_model: 'fp32'" in html
    assert "decoder_model_merged: 'q4'" in html
    assert 'actualDevice' in html
    assert 'withBrowserWhisperTimeout' in html
    assert 'browser-whisper-webgpu' in html
    assert 'browser-whisper-wasm' in html
    assert 'const browserStartedAt = performance.now();' in html
    assert 'duration_seconds: duration' in html
    assert 'processing_seconds: Math.max(0.1' in html
    assert "wordCount(rec.transcript || '')" in html
    assert 'words${dur}${proc}' in html
    assert 'chars${dur}${proc}' not in html
    assert 'segments: Array.isArray(rec.segments) ? rec.segments : []' in html
    assert "language: rec.language || ''" in html


def test_faqs_and_theme_toggle_are_present():
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
    assert "☀" in html
    assert "☾" in html


def test_vtt_download_and_owner_headers_are_available():
    html = HTML.read_text()
    assert 'id="downloadVttBtn"' in html
    assert "els.downloadVttBtn.addEventListener('click', () => downloadCurrent('vtt'))" in html
    assert "WEBVTT" in html
    assert "X-Transcript-Owner" in html
    assert "/api/transcripts/" in html
    assert "/download-link?format=" in html
