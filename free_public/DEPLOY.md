# Deploy the free public transcriber

This is a new service. Leave these alone:

- `https://epic-transcript.robyncrane.com/`
- `https://epicmachines.ai/transcribe`
- the iMac process on port 8090
- the Cloudflare tunnel, including the previously blocked outbound route on port 7844
- `static/index.html` and the root `Dockerfile` (that image still installs a local speech model for the existing host)

## Render Free

`render.yaml` at the repo root defines one Docker web service:

- name: `epic-transcript-free-public`
- plan: `free` (512MB RAM, 0.1 CPU)
- context: `free_public/`
- health check: `/health`
- data dir: `/tmp/transcript-data` (ephemeral; a persistent disk is a paid Render add-on and is not configured)

`/health` reports `transcription: captions-only`, `whisper: false`, and `paid_providers: []`. A static page is not this service.

## What this environment cannot do

Checked from the build machine:

- `RENDER_API_KEY` is unset
- the `render` CLI is not installed
- the connected Composio apps do not include Render

Do not create a Render account, choose a paid plan, or enter a card from this change. After a Render connector or an existing account's API key is available to a later run, deploy the blueprint as the free service above. The parent can install that connector separately.

No public URL is claimed until that deploy exists and `/health` answers from it.
