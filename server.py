#!/usr/bin/env python3
"""
AI Captain Server — FastAPI + Feishu OAuth
- Serves static SPA from dist/
- /api/sync — GitHub data sync
- /api/auth/feishu/* — Feishu OAuth login
"""
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
DATA_FILE = ROOT / "public" / "data.json"
SYNC_SCRIPT = ROOT / "scripts" / "auto_sync_projects.py"

# ── Config ───────────────────────────────────────
DEPLOY_MODE = os.getenv("DEPLOY_MODE", "local")  # "local" or "cloud"
BASE_PATH = "/ai-captain-dashboard"
PORT = int(os.getenv("PORT", "4175"))

# Feishu OAuth
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_REDIRECT_URI = os.getenv(
    "FEISHU_REDIRECT_URI",
    f"https://ai.goodideaggn.com{BASE_PATH}/api/auth/feishu/callback",
)
JWT_SECRET = os.getenv("JWT_SECRET", "ai-captain-dev-secret-change-me")
JWT_EXPIRY = 86400 * 7  # 7 days

# ── State ────────────────────────────────────────
_oauth_states: dict[str, float] = {}  # state -> expiry_ts
_app_token_cache: dict[str, tuple[str, float]] = {}  # key -> (token, expiry)

app = FastAPI(title="AI Captain", root_path="")


# ── Auth Helpers ─────────────────────────────────
def auth_enabled() -> bool:
    return DEPLOY_MODE == "cloud" and bool(FEISHU_APP_ID)


async def get_feishu_app_token() -> str:
    """Get or refresh Feishu app_access_token."""
    cached = _app_token_cache.get("app")
    if cached and cached[1] > time.time():
        return cached[0]

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        )
        data = r.json()
        token = data.get("app_access_token", "")
        expire = data.get("expire", 7200)
        _app_token_cache["app"] = (token, time.time() + expire - 300)
        return token


def create_jwt(user_id: str, name: str, avatar: str = "") -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "name": name,
            "avatar": avatar,
            "exp": int(time.time()) + JWT_EXPIRY,
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def get_current_user(request: Request) -> dict | None:
    """Extract user from Authorization header or query param."""
    if not auth_enabled():
        return {"sub": "local", "name": "Local Dev"}

    token = None
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    else:
        token = request.query_params.get("token")

    if not token:
        return None
    return decode_jwt(token)


def require_auth(user=Depends(get_current_user)):
    if auth_enabled() and user is None:
        raise HTTPException(401, "Unauthorized")
    return user


# ── Auth Routes ──────────────────────────────────
@app.get(f"{BASE_PATH}/api/auth/feishu/login")
async def feishu_login():
    if not auth_enabled():
        return {"url": None, "mode": "local"}

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time() + 300  # 5 min TTL

    # Cleanup expired states
    now = time.time()
    expired = [k for k, v in _oauth_states.items() if v < now]
    for k in expired:
        del _oauth_states[k]

    url = (
        f"https://open.feishu.cn/open-apis/authen/v1/authorize"
        f"?app_id={FEISHU_APP_ID}"
        f"&redirect_uri={FEISHU_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )
    return {"url": url, "state": state}


@app.get(f"{BASE_PATH}/api/auth/feishu/callback")
async def feishu_callback(code: str = "", state: str = ""):
    if not auth_enabled():
        return RedirectResponse(f"{BASE_PATH}/")

    # Verify state
    if state not in _oauth_states or _oauth_states[state] < time.time():
        raise HTTPException(400, "Invalid or expired state")
    del _oauth_states[state]

    # Exchange code for user token
    app_token = await get_feishu_app_token()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
            headers={"Authorization": f"Bearer {app_token}"},
            json={"grant_type": "authorization_code", "code": code},
        )
        token_data = r.json().get("data", {})
        user_access_token = token_data.get("access_token", "")

        if not user_access_token:
            raise HTTPException(400, f"Failed to get access token: {r.text}")

        # Get user info
        r2 = await client.get(
            "https://open.feishu.cn/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {user_access_token}"},
        )
        user_info = r2.json().get("data", {})

    open_id = user_info.get("open_id", "")
    name = user_info.get("name", "Unknown")
    avatar = user_info.get("avatar_url", "")

    # Issue JWT
    token = create_jwt(open_id, name, avatar)

    # Redirect to frontend with token in fragment
    return RedirectResponse(f"{BASE_PATH}/#token={token}")


@app.get(f"{BASE_PATH}/api/auth/me")
async def auth_me(user=Depends(require_auth)):
    return {
        "user_id": user.get("sub"),
        "name": user.get("name"),
        "avatar": user.get("avatar", ""),
    }


@app.get(f"{BASE_PATH}/api/health")
async def health():
    return {"status": "ok", "mode": DEPLOY_MODE, "auth": auth_enabled()}


# ── Sync Route ───────────────────────────────────
@app.post(f"{BASE_PATH}/api/sync")
@app.get(f"{BASE_PATH}/api/sync")
async def sync_data(user=Depends(require_auth)):
    try:
        cmd = [sys.executable, str(SYNC_SCRIPT), "--write", "--with-issues"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        if result.returncode != 0:
            return JSONResponse(
                500,
                {"ok": False, "error": result.stderr[-500:] if result.stderr else "sync failed"},
            )

        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text())
            # Copy to dist for static serving
            dist_data = DIST / "data.json"
            if DIST.exists():
                dist_data.write_text(DATA_FILE.read_text())
            return {
                "ok": True,
                "projects": len(data.get("projects", [])),
                "tasks": len(data.get("tasks", [])),
                "conditions": len(data.get("conditions", [])),
                "data": data,
            }
        return JSONResponse(500, {"ok": False, "error": "data.json not found"})

    except subprocess.TimeoutExpired:
        return JSONResponse(504, {"ok": False, "error": "sync timed out"})
    except Exception as e:
        return JSONResponse(500, {"ok": False, "error": str(e)})


# ── Confirm Milestone → Sync to GitHub ───────────
@app.post(f"{BASE_PATH}/api/confirm-milestone")
async def confirm_milestone(request: Request, user=Depends(require_auth)):
    body = await request.json()
    milestone_id = body.get("milestoneId", "")

    data = json.loads(DATA_FILE.read_text())

    milestone = next((m for m in data.get("milestones", []) if m["id"] == milestone_id), None)
    if not milestone:
        raise HTTPException(404, "Milestone not found")
    if milestone.get("confirmed"):
        return {"ok": True, "already_confirmed": True}

    project = next((p for p in data["projects"] if p["id"] == milestone["projectId"]), None)
    if not project:
        raise HTTPException(404, "Project not found")

    repo = project.get("githubRepo") or f"goodidea-ggn/{project['id']}"
    gh_title = f"{milestone['label']}: {milestone['title']}"
    gh_desc = f"目标: {milestone['goal']}"

    # Create GitHub milestone
    r = subprocess.run(
        ["gh", "api", f"repos/{repo}/milestones", "--method", "POST",
         "-f", f"title={gh_title}", "-f", f"description={gh_desc}"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise HTTPException(500, f"GitHub milestone creation failed: {r.stderr[-300:]}")

    gh_milestone_number = json.loads(r.stdout)["number"]

    # Create issues for each condition in this milestone
    conditions = [c for c in data["conditions"] if c.get("milestoneId") == milestone_id]
    for c in conditions:
        subprocess.run(
            ["gh", "issue", "create", "--repo", repo,
             "--title", c["name"], "--body", f"Milestone: {gh_title}",
             "--milestone", gh_title],
            capture_output=True, text=True
        )

    # Mark confirmed in data.json
    for m in data["milestones"]:
        if m["id"] == milestone_id:
            m["confirmed"] = True
            break
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    dist_data = DIST / "data.json"
    if DIST.exists():
        dist_data.write_text(DATA_FILE.read_text())

    return {"ok": True, "milestone": gh_title, "issues_created": len(conditions), "gh_number": gh_milestone_number}


# ── Static SPA Serving ───────────────────────────
# Mount static assets (JS/CSS/images)
if DIST.exists():
    app.mount(
        f"{BASE_PATH}/assets",
        StaticFiles(directory=str(DIST / "assets")),
        name="assets",
    )


@app.get(f"{BASE_PATH}/data.json")
async def serve_data():
    """Serve data.json (public, no auth needed for initial load)."""
    f = DATA_FILE  # Always read from public/ (source of truth), not dist/
    return FileResponse(f, media_type="application/json")


@app.get(f"{BASE_PATH}/{{path:path}}")
async def serve_spa(path: str):
    """SPA fallback — serve index.html for all non-API routes."""
    # Try exact file first
    file_path = DIST / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    # Fallback to index.html
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(404, {"error": "Not found. Run 'npm run build' first."})


# ── Redirect bare path ───────────────────────────
@app.get("/ai-captain-dashboard")
async def redirect_to_trailing():
    return RedirectResponse(f"{BASE_PATH}/", status_code=301)


def main():
    import uvicorn

    if not DIST.exists():
        print(f"⚠️  {DIST} not found. Run 'npm run build' first.")
        print(f"   Starting anyway for API-only mode...")

    print(f"🚀 AI Captain on http://localhost:{PORT}{BASE_PATH}/")
    print(f"   Mode: {DEPLOY_MODE} | Auth: {auth_enabled()}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
