# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A web app that takes an image of a festival lineup poster, uses AI vision to extract artist names, then creates a Spotify playlist with tracks from those artists. FastAPI backend, vanilla JS frontend.

## Development

```bash
# Setup (uses uv for dependency management)
uv sync

# Copy .env.example to .env and fill in credentials
cp .env.example .env

# Run dev server
uv run uvicorn main:app --reload
```

The app runs at `http://localhost:8000`. The Spotify redirect URI must match `SPOTIFY_REDIRECT_URI` in `.env` (default: `http://localhost:8000/callback`).

No test suite or linter is configured. Python 3.14+ is required.

## Architecture

Single-file backend (`main.py`) with all endpoints. Frontend is vanilla JS/CSS/HTML served from `static/` (plus legal pages: privacy policy, cookie policy, terms). The static mount is last in `main.py` so it doesn't shadow API routes.

**Auth flow:** Spotify OAuth2 Authorization Code Flow. Tokens stored in server-side signed session cookies (Starlette `SessionMiddleware`). The `/login` endpoint redirects to Spotify, `/callback` exchanges the code for tokens and stores them in the session.

**Core flow:**
1. `POST /extract` — receives uploaded image, base64-encodes it, sends to a vision model via LiteLLM, parses returned JSON with `festival_name`, `year`, and `artists` fields
2. Frontend shows an editable checklist so the user can remove false positives or add missing artists
3. `POST /create-playlist` — searches Spotify for tracks per artist (concurrency-limited with `asyncio.Semaphore(5)`), creates a playlist, adds tracks in batches of 100
4. `GET /playlists` — lists user's playlists created by this app (identified by description prefix)

**AI provider:** LiteLLM wraps the vision call, so the model is configurable via `LITELLM_MODEL` env var (default: `gpt-4o`) without code changes. Set the corresponding API key env var (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

**Spotify API:** Direct `httpx.AsyncClient` calls (no Spotipy). Token refresh is handled automatically in `ensure_valid_token()`. Track search uses `artist:{name}` query and filters results to exact artist name matches (case-insensitive). `TRACKS_PER_ARTIST` env var controls how many tracks per artist (default 3, max 10).
