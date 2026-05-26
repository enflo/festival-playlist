# Festival Playlist

Upload a festival lineup poster, and this app uses AI vision to extract the artist names and creates a Spotify playlist with tracks from those artists.

## How it works

1. Upload an image of a festival lineup poster
2. AI extracts artist names from the image
3. Review and edit the artist list (remove false positives, add missing names)
4. The app searches Spotify for tracks by each artist and creates a playlist

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A [Spotify Developer](https://developer.spotify.com/dashboard) app (for Client ID and Secret)
- An API key for an AI vision model (e.g. OpenAI, Anthropic)

## Setup

```bash
git clone https://github.com/enflo/festival-playlist.git
cd festival-playlist
uv sync
cp .env.example .env
```

Edit `.env` with your credentials (see below), then start the server:

```bash
uv run uvicorn main:app --reload
```

The app runs at `http://localhost:8000`.

### Spotify app configuration

In your [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), add `http://localhost:8000/callback` as a Redirect URI for your app.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SPOTIFY_CLIENT_ID` | Yes | | Spotify app Client ID |
| `SPOTIFY_CLIENT_SECRET` | Yes | | Spotify app Client Secret |
| `SPOTIFY_REDIRECT_URI` | No | `http://localhost:8000/callback` | OAuth redirect URI |
| `SESSION_SECRET` | No | Random | Secret key for session cookies |
| `LITELLM_MODEL` | No | `gpt-4o` | AI model for vision extraction (via [LiteLLM](https://docs.litellm.ai/)) |
| `OPENAI_API_KEY` | Depends | | Required if using an OpenAI model |
| `ANTHROPIC_API_KEY` | Depends | | Required if using an Anthropic model |
| `TRACKS_PER_ARTIST` | No | `3` | Number of tracks per artist (max 10) |

## Tech stack

- **Backend:** FastAPI (single-file `main.py`)
- **Frontend:** Vanilla JS/CSS/HTML
- **AI:** LiteLLM (supports OpenAI, Anthropic, and other providers)
- **Spotify:** Direct API calls with `httpx` (OAuth2 Authorization Code Flow)

## License

[MIT](LICENSE)
