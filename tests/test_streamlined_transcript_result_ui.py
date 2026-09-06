from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_result_controls_are_exact_streamlined_layout_above_transcript():
    html = HTML.read_text()
    result = html[html.index('id="result"'):html.index('</section>', html.index('id="result"'))]
    assert result.index('class="actions"') < result.index('id="transcript"')
    assert result.index('id="questionInput"') < result.index('id="transcript"')
    for required in [
        'id="copyBtn"',
        'id="downloadMenu"',
        'Download ▾',
        'data-format="txt"',
        'Plain Text',
        'data-format="md"',
        'Markdown',
        'data-format="srt"',
        'Subtitles',
        'id="summaryBtn"',
        'Summary',
        'id="actionsBtn"',
        'Action Items',
        'id="questionInput"',
        'Quotes · Chapters · Hooks · FAQ',
        'id="askBtn"',
    ]:
        assert required in result
    for retired in [
        'downloadFormat',
        'All Outputs',
        'Copy Analysis',
        'Download Analysis',
        'Email to Me',
        'AI Summary',
        'VTT',
        'Create 100 content assets',
        'Best quotes',
        'Blog post',
    ]:
        assert retired not in result


def test_how_it_works_disappears_after_transcript_is_ready():
    html = HTML.read_text()
    assert 'id="how"' in html
    assert 'function hideHowAfterTranscriptReady()' in html
    render = html[html.index('function renderResult(rec)'):html.index('function wordCount')]
    assert 'hideHowAfterTranscriptReady();' in render
    assert "els.how.classList.add('hidden-after-result')" in html
    assert '.how-stage.hidden-after-result { display:none; }' in html
