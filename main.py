import asyncio
import base64
import json
import logging
import os
import re
import secrets
import time

import httpx

import litellm
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

litellm.suppress_debug_info = True

load_dotenv()

SPOTIFY_CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback"
)
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gpt-4o")
TRACKS_PER_ARTIST = min(int(os.getenv("TRACKS_PER_ARTIST", "3")), 10)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API = "https://api.spotify.com/v1"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private user-read-private"

SPOTIFY_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

log = logging.getLogger(__name__)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def ensure_valid_token(request: Request) -> str:
    """Return a valid Spotify access token, refreshing if needed."""
    token = request.session.get("access_token")
    if not token:
        raise HTTPException(401, "Not authenticated")

    if time.time() > request.session.get("expires_at", 0):
        refresh = request.session.get("refresh_token")
        if not refresh:
            raise HTTPException(401, "Session expired, please log in again")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SPOTIFY_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": SPOTIFY_CLIENT_ID,
                    "client_secret": SPOTIFY_CLIENT_SECRET,
                },
            )
        if resp.status_code != 200:
            request.session.clear()
            raise HTTPException(401, "Token refresh failed, please log in again")
        data = resp.json()
        request.session["access_token"] = data["access_token"]
        request.session["expires_at"] = time.time() + data["expires_in"] - 60
        if "refresh_token" in data:
            request.session["refresh_token"] = data["refresh_token"]
        token = data["access_token"]
    return token


async def search_artist_tracks(
    client: httpx.AsyncClient,
    token: str,
    artist: str,
    limit: int,
    sem: asyncio.Semaphore,
) -> tuple[str, list[str]]:
    """Search Spotify for tracks by an artist. Returns (artist, [track_uris])."""
    try:
        async with sem:
            resp = await client.get(
                f"{SPOTIFY_API}/search",
                params={"q": f"artist:{artist}", "type": "track", "limit": limit},
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            await asyncio.sleep(retry_after)
            async with sem:
                resp = await client.get(
                    f"{SPOTIFY_API}/search",
                    params={"q": f"artist:{artist}", "type": "track", "limit": limit},
                    headers={"Authorization": f"Bearer {token}"},
                )
        if resp.status_code != 200:
            return artist, []
        items = resp.json().get("tracks", {}).get("items", [])
        artist_lower = artist.lower()
        matched = [
            t["uri"]
            for t in items
            if any(a["name"].lower() == artist_lower for a in t.get("artists", []))
        ]
        return artist, matched
    except httpx.HTTPError:
        return artist, []


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{SPOTIFY_AUTH_URL}?{qs}")


@app.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"Spotify auth error: {error}")
    if state != request.session.get("oauth_state"):
        raise HTTPException(400, "State mismatch")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "client_id": SPOTIFY_CLIENT_ID,
                "client_secret": SPOTIFY_CLIENT_SECRET,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(502, "Failed to exchange code for token")
    data = resp.json()
    request.session["access_token"] = data["access_token"]
    request.session["refresh_token"] = data.get("refresh_token", "")
    request.session["expires_at"] = time.time() + data["expires_in"] - 60

    async with httpx.AsyncClient() as client:
        me = await client.get(
            f"{SPOTIFY_API}/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
    if me.status_code == 200:
        profile = me.json()
        request.session["user_id"] = profile["id"]
        request.session["display_name"] = profile.get("display_name", profile["id"])

    return RedirectResponse("/")


@app.get("/me")
async def me(request: Request):
    if request.session.get("access_token"):
        return {
            "logged_in": True,
            "display_name": request.session.get("display_name", ""),
        }
    return {"logged_in": False}


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"logged_in": False}


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------


@app.get("/playlists")
async def get_playlists(request: Request):
    token = await ensure_valid_token(request)
    playlists = []
    url = f"{SPOTIFY_API}/me/playlists?limit=50"
    max_pages = 10
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=SPOTIFY_TIMEOUT) as client:
        for _ in range(max_pages):
            if not url:
                break
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                break
            data = resp.json()
            for p in data.get("items") or []:
                if (p.get("description") or "").startswith(
                    "Created from a festival lineup poster"
                ):
                    images = p.get("images") or []
                    playlists.append(
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "url": p["external_urls"]["spotify"],
                            "tracks": 0,
                            "image": images[0]["url"] if images else None,
                        }
                    )
            url = data.get("next")

        # Fetch real track counts from each playlist individually
        async def fetch_track_count(playlist: dict) -> None:
            resp = await client.get(
                f"{SPOTIFY_API}/playlists/{playlist['id']}/tracks?fields=total&limit=0",
                headers=headers,
            )
            if resp.status_code == 200:
                playlist["tracks"] = resp.json().get("total", 0)

        await asyncio.gather(*(fetch_track_count(p) for p in playlists))

    return {"playlists": playlists}


@app.post("/extract")
async def extract_artists(request: Request, file: UploadFile):
    await ensure_valid_token(request)

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, "Image exceeds 10 MB limit")

    ext = file.content_type.split("/")[1]
    b64 = base64.b64encode(data).decode()
    data_uri = f"data:image/{ext};base64,{b64}"

    try:
        response = await litellm.acompletion(
            model=LITELLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This is a music festival lineup poster. "
                                "Extract the festival name, the year, and every band/artist name visible on this poster. "
                                'Return ONLY a JSON object with keys "festival_name", "year", and "artists". '
                                '"artists" is an array of strings. "festival_name" is a string. "year" is a string (e.g. "2025"). '
                                "If the year is not visible, make your best guess or use an empty string. "
                                'Example: {"festival_name": "Coachella", "year": "2025", "artists": ["Radiohead", "LCD Soundsystem", "Tame Impala"]}'
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        )
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}")

    text = response.choices[0].message.content.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                raise HTTPException(422, "Could not parse AI response")
        else:
            raise HTTPException(422, "Could not parse AI response")

    if isinstance(parsed, list):
        # Fallback: model returned a plain array
        artists = parsed
        festival_name = ""
        year = ""
    elif isinstance(parsed, dict):
        artists = parsed.get("artists", [])
        festival_name = parsed.get("festival_name", "")
        year = parsed.get("year", "")
    else:
        raise HTTPException(422, "AI returned unexpected format")

    if not isinstance(artists, list) or not all(isinstance(a, str) for a in artists):
        raise HTTPException(422, "AI returned unexpected format")

    playlist_name = (
        f"{festival_name} {year}".strip() if festival_name else "Festival Playlist"
    )

    return {"artists": artists, "playlist_name": playlist_name}


class PlaylistRequest(BaseModel):
    artists: list[str]
    playlist_name: str = "Festival Playlist"
    tracks_per_artist: int = TRACKS_PER_ARTIST


@app.post("/create-playlist")
async def create_playlist(request: Request, body: PlaylistRequest):
    token = await ensure_valid_token(request)

    sem = asyncio.Semaphore(5)
    async with httpx.AsyncClient(timeout=SPOTIFY_TIMEOUT) as client:
        tasks = [
            search_artist_tracks(
                client, token, artist, min(body.tracks_per_artist, 10), sem
            )
            for artist in body.artists
        ]
        results = await asyncio.gather(*tasks)

    track_uris: list[str] = []
    not_found: list[str] = []
    for artist, uris in results:
        if uris:
            track_uris.extend(uris)
        else:
            not_found.append(artist)

    if not track_uris:
        raise HTTPException(404, "No tracks found for any of the listed artists")

    async with httpx.AsyncClient(timeout=SPOTIFY_TIMEOUT) as client:
        resp = await client.post(
            f"{SPOTIFY_API}/me/playlists",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "name": body.playlist_name,
                "public": False,
                "description": "Created from a festival lineup poster",
            },
        )
    if resp.status_code not in (200, 201):
        log.error("Playlist creation failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(502, f"Failed to create playlist: {resp.text}")
    playlist = resp.json()
    playlist_id = playlist["id"]
    playlist_url = playlist["external_urls"]["spotify"]

    # Add tracks in batches of 100
    async with httpx.AsyncClient(timeout=SPOTIFY_TIMEOUT) as client:
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i : i + 100]
            resp = await client.post(
                f"{SPOTIFY_API}/playlists/{playlist_id}/items",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"uris": batch},
            )
            if resp.status_code not in (200, 201):
                log.error("Add tracks failed: %s %s", resp.status_code, resp.text)
                raise HTTPException(502, f"Failed to add tracks: {resp.text}")

    return {
        "playlist_url": playlist_url,
        "tracks_added": len(track_uris),
        "artists_not_found": not_found,
    }


# ---------------------------------------------------------------------------
# Static files (must be last so it doesn't shadow API routes)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="static", html=True), name="static")
