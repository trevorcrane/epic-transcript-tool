# Free public transcriber

A separate two-button YouTube transcriber for a small container. It does not replace the existing public site.

- **Transcript only** reads captions with yt-dlp, then the YouTube transcript library if needed.
- **Transcript with screenshots** keeps that transcript, downloads a 360p copy, and builds a timestamped JPEG gallery plus a ZIP.
- If the screenshot stage fails, the transcript is still returned with the note `Screenshots could not be captured.`

This runtime does not install a speech model and does not call a paid transcription API. Render Free is 512MB and 0.1 CPU. A Whisper/torch image exceeds that memory budget, so videos without captions return a clear error instead of a hidden fallback.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r free_public/requirements.txt
export PYTHONPATH=free_public/src
export TRANSCRIPT_DATA_DIR=/tmp/transcript-data
python -m free_public.app
```

Open `http://127.0.0.1:8090/`. `PORT` overrides 8090. ffmpeg must be on `PATH`. When `node` is on `PATH`, yt-dlp is started with `--js-runtimes`. That is the current YouTube extractor requirement. It does not pass cookies or a proxy. `--ignore-config` is set so a developer config file cannot add them.

## Tests

```bash
PYTHONPATH=free_public/src pytest free_public/tests -q
```

## Deploy

See `DEPLOY.md` and the repo-root `render.yaml`. The service name is `epic-transcript-free-public`. Pointing the existing Cloudflare hostname at this service is out of scope.
