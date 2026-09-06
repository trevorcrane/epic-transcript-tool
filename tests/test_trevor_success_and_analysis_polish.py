from pathlib import Path

from app import build_analysis_text, row_to_record, segments_to_transcript

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_success_message_replaces_quick_line_with_bold_wipe_personality():
    html = HTML.read_text()
    assert "Quick and simple. No catch." in html
    assert "const SUCCESS_MESSAGES" in html
    for phrase in ["Boom!", "Done!", "Success!", "Awesomeness!"]:
        assert phrase in html
    assert "function showSuccessMessage" in html
    assert "success-wipe" in html
    assert ".proof-strip span:not(.success-wipe)" in html
    assert "showSuccessMessage();" in html


def test_result_padding_gets_much_tighter_after_transcript_ready():
    html = HTML.read_text()
    assert ".light-stage.compact-after-result" in html
    assert "els.lightStage.classList.add('compact-after-result')" in html


def test_copy_dropdown_offers_transcript_format_variants():
    html = HTML.read_text()
    result = html[html.index('id="result"'):html.index('</section>', html.index('id="result"'))]
    assert 'id="copyMenu"' in result
    assert 'Copy ▾' in result
    assert 'data-copy-format="txt"' in result and 'Copy .txt' in result
    assert 'data-copy-format="md"' in result and 'Copy .md' in result
    assert 'data-copy-format="srt"' in result and 'Copy .srt' in result
    assert "copyCurrent(btn.dataset.copyFormat || 'txt')" in html
    assert "formatTranscriptForCopy(format)" in html
    assert "function copyTextToClipboard" in html
    assert "document.execCommand('copy')" in html


def test_analysis_result_has_top_copy_icon():
    html = HTML.read_text()
    panel = html[html.index('id="analysisPanel"'):html.index('id="transcript"')]
    assert 'id="copyAnalysisBtn"' in panel
    assert 'aria-label="Copy analysis result"' in panel
    assert "copyAnalysisBtn" in html
    assert "copyTextToClipboard(els.analysisBox.textContent || '')" in html


def test_dedupes_adjacent_caption_overlap_in_transcript_text():
    segs = [
        {"start": 0, "end": 2, "text": "Stop prompting Claude use this method instead"},
        {"start": 2, "end": 4, "text": "Claude use this method instead it is one hundred percent free"},
        {"start": 4, "end": 6, "text": "it is one hundred percent free and works faster"},
    ]
    transcript = segments_to_transcript(segs)
    assert "Claude use this method instead Claude use this method instead" not in transcript
    assert "it is one hundred percent free it is one hundred percent free" not in transcript
    assert transcript.count("Claude use this method instead") == 1
    assert transcript.count("it is one hundred percent free") == 1


def test_cached_record_readback_rebuilds_transcript_from_deduped_segments():
    row = {
        "id": "cached-overlap",
        "source": "sample",
        "source_kind": "upload",
        "method": "captions",
        "transcript": "[00:00] Stop prompting Claude use this method instead\n[00:02] Claude use this method instead it is one hundred percent free",
        "duration_seconds": 6,
        "processing_seconds": 1,
        "media_id": "sample",
        "source_url": "sample",
        "title": "sample",
        "creator": "",
        "language": "en",
        "segments_json": '[{"start":0,"end":2,"text":"Stop prompting Claude use this method instead"},{"start":2,"end":4,"text":"Claude use this method instead it is one hundred percent free"}]',
        "provider_attempts_json": "[]",
        "word_count": 0,
        "owner_token": "owner",
        "created_at": "now",
    }
    rec = row_to_record(row)
    assert rec["transcript"].count("Claude use this method instead") == 1


def test_summary_and_action_items_are_useful_without_random_timestamp_header():
    rec = {
        "title": "Stop prompting Claude. Use this method instead",
        "word_count": 900,
        "segments": [
            {"start": 0, "end": 5, "text": "Most people prompt Claude randomly and get generic answers."},
            {"start": 35, "end": 42, "text": "Start with the outcome, then give context, constraints, examples, and the exact output format."},
            {"start": 80, "end": 90, "text": "Create reusable prompt templates so every assistant starts from the same standard."},
            {"start": 120, "end": 130, "text": "Review the output against a checklist and rewrite the prompt if it misses the mark."},
        ],
    }
    summary = build_analysis_text(rec, "executive_summary")
    actions = build_analysis_text(rec, "action_items")
    for text in [summary, actions]:
        assert "Words reviewed:" not in text
        assert "Transcript evidence" not in text
        assert "AI-generated" not in text
        assert "## Source notes" in text
        assert "[00:" in text
    assert "## Quick summary" in summary
    assert "## Why this matters" in summary
    assert "## Use this next" in summary
    assert "## Action plan" in actions
    assert "Owner:" in actions
    assert "Outcome:" in actions
    assert "First step:" in actions
    assert "Done when:" in actions


def test_gemini_prompt_is_scored_rewritten_and_95_plus_documented():
    html = HTML.read_text()
    doc = Path(__file__).resolve().parents[1] / "PROMPT_REVIEW_SUMMARY_ACTIONS.md"
    assert doc.exists()
    text = doc.read_text()
    assert "Round 1 score:" in text
    assert "Round 2 score:" in text
    assert "Final score: 96/100" in text or "Final score: 97/100" in text or "Final score: 98/100" in text
    assert "Final Summary Prompt" in text
    assert "Final Action Items Prompt" in text
