from __future__ import annotations

import base64
import datetime
import hashlib
import html
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
WORKSPACE = APP_DIR.parent
PROFILE_ROOT = WORKSPACE / "chatgpt-profiles"
DELETED_ROOT = WORKSPACE / "deleted-profiles"
AUTH_LINKS_FILE = WORKSPACE / "auth-links.json"
WEB_ROOT = APP_DIR / "web"
META_FILE = ".profile-meta.json"
DEFAULT_URL = "https://chatgpt.com"
AUTH_ISSUER = "https://auth.openai.com"
AUTH_DISCOVERY_URL = f"{AUTH_ISSUER}/.well-known/openid-configuration"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_SCOPES = "openid profile email offline_access api.connectors.read api.connectors.invoke"
CODEX_DEVICE_URL = "https://auth.openai.com/codex/device"
DEFAULT_CALLBACK_PORT = 1455
LOGIN_PROCS: dict[str, dict] = {}
OAUTH_LOGINS: dict[str, dict] = {}
OAUTH_LOCK = threading.Lock()
OAUTH_CALLBACK_LOCK = threading.Lock()
OAUTH_CALLBACK_SERVER = None
OAUTH_CALLBACK_PORT = 0
AUTH_CONFIG: dict | None = None


def now_ms() -> int:
    return int(time.time() * 1000)


def find_chrome() -> str:
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        raise RuntimeError("Google Chrome was not found. Install Google Chrome in /Applications.")

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / "chrome.exe"
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Google Chrome was not found.")


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", name.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._ ")
    if not cleaned:
        raise ValueError("Profile name cannot be empty.")
    if cleaned in {".", ".."}:
        raise ValueError("Invalid profile name.")
    return cleaned


def profile_dir(name: str) -> Path:
    cleaned = safe_name(name)
    target = (PROFILE_ROOT / cleaned).resolve()
    root = PROFILE_ROOT.resolve()
    if root != target and root not in target.parents:
        raise ValueError("Profile path escaped the profile root.")
    return target


def profile_codex_home(name: str) -> Path:
    return profile_dir(name) / "codex-home"


def official_auth_path(name: str) -> Path:
    return profile_codex_home(name) / "auth.json"


def official_auth_record(name: str) -> dict:
    path = official_auth_path(name)
    if not path.exists():
        return {"ready": False, "updatedAt": None, "path": str(path)}
    stat = path.stat()
    record = {"ready": True, "updatedAt": int(stat.st_mtime * 1000), "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        tokens = payload.get("tokens") if isinstance(payload, dict) else None
        id_token = tokens.get("id_token") if isinstance(tokens, dict) else None
        claims = decode_jwt_payload(id_token) if id_token else {}
        auth_claims = claims.get("https://api.openai.com/auth") if isinstance(claims, dict) else {}
        profile = (payload.get("tokens") or {}) if isinstance(payload, dict) else {}
        record.update(
            {
                "authMode": payload.get("auth_mode"),
                "email": claims.get("email") or "",
                "accountId": profile.get("account_id") or auth_claims.get("chatgpt_account_id") or "",
                "planType": auth_claims.get("chatgpt_plan_type") or "",
                "lastRefresh": payload.get("last_refresh") or "",
                "hasAccessToken": bool(profile.get("access_token")),
                "hasRefreshToken": bool(profile.get("refresh_token")),
            }
        )
    except Exception:
        record["parseError"] = True
    return record


def decode_jwt_payload(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        import base64

        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


def read_meta(path: Path) -> dict:
    meta_path = path / META_FILE
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_meta(path: Path, meta: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    meta_path = path / META_FILE
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def profile_record(path: Path) -> dict:
    meta = read_meta(path)
    stat = path.stat()
    name = path.name
    return {
        "name": name,
        "email": meta.get("email", ""),
        "status": meta.get("status", "empty"),
        "note": meta.get("note", ""),
        "createdAt": meta.get("createdAt") or int(stat.st_ctime * 1000),
        "updatedAt": meta.get("updatedAt") or int(stat.st_mtime * 1000),
        "lastOpenedAt": meta.get("lastOpenedAt"),
        "dir": str(path),
        "officialAuth": official_auth_record(name),
    }


def list_profiles() -> list[dict]:
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    records = []
    for path in PROFILE_ROOT.iterdir():
        if path.is_dir():
            records.append(profile_record(path))
    records.sort(key=lambda item: (int(item.get("createdAt") or 0), natural_key(item["name"])), reverse=True)
    return records


def export_profile(name: str) -> dict:
    path = profile_dir(name)
    if not path.exists():
        raise FileNotFoundError(name)
    record = profile_record(path)
    return {
        "type": "chatgpt-profile-auth",
        "version": 1,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "profile": {
            "name": record["name"],
            "email": record["email"],
            "status": record["status"],
            "note": record["note"],
            "chrome_user_data_dir": record["dir"],
            "last_opened_at": record["lastOpenedAt"],
        },
    }


def export_all_profiles() -> dict:
    return {
        "type": "chatgpt-profile-auth-list",
        "version": 1,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "profiles": [export_profile(item["name"])["profile"] for item in list_profiles()],
    }


def default_auth_links() -> list[dict]:
    return [
        {
            "id": "chatgpt",
            "label": "1 官方登录网站",
            "url": DEFAULT_URL,
            "createdAt": 0,
            "updatedAt": 0,
        },
        {
            "id": "openai-auth",
            "label": "2 Auth 授权网站",
            "url": "https://auth.openai.com",
            "createdAt": 0,
            "updatedAt": 0,
        },
        {
            "id": "register-yangmao",
            "label": "3 注册账号网站（羊毛）",
            "url": "https://invite.kyl23333.xyz/",
            "createdAt": 0,
            "updatedAt": 0,
        },
    ]


def read_auth_links() -> list[dict]:
    if not AUTH_LINKS_FILE.exists():
        write_auth_links(default_auth_links())
        return default_auth_links()
    try:
        payload = json.loads(AUTH_LINKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        payload = []
    raw_links = payload.get("links", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_links, list):
        raw_links = []

    links = []
    seen_ids = set()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        try:
            url = normalize_url(str(item.get("url") or ""))
        except ValueError:
            continue
        label = str(item.get("label") or urllib.parse.urlparse(url).netloc or url).strip()
        link_id = safe_link_id(str(item.get("id") or label or url), seen_ids)
        created_at = int(item.get("createdAt") or now_ms())
        updated_at = int(item.get("updatedAt") or created_at)
        links.append(
            {
                "id": link_id,
                "label": label,
                "url": url,
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )
        seen_ids.add(link_id)

    if not links:
        links = default_auth_links()
    return links


def write_auth_links(links: list[dict]) -> None:
    payload = {
        "version": 1,
        "updatedAt": now_ms(),
        "links": links,
    }
    AUTH_LINKS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_link_id(value: str, used: set[str] | None = None) -> str:
    used = used or set()
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    if not base:
        base = "link"
    link_id = base[:48]
    suffix = 2
    while link_id in used:
        tail = f"-{suffix}"
        link_id = f"{base[:48 - len(tail)]}{tail}"
        suffix += 1
    return link_id


def create_auth_link(label: str, url: str) -> dict:
    normalized_url = normalize_url(url)
    label = (label or "").strip() or urllib.parse.urlparse(normalized_url).netloc or normalized_url
    links = read_auth_links()
    used = {item["id"] for item in links}
    timestamp = now_ms()
    link = {
        "id": safe_link_id(f"{label}-{timestamp}", used),
        "label": label,
        "url": normalized_url,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    links.append(link)
    write_auth_links(links)
    return link


def delete_auth_link(link_id: str) -> dict:
    links = read_auth_links()
    kept = [item for item in links if item["id"] != link_id]
    if len(kept) == len(links):
        raise FileNotFoundError(link_id)
    write_auth_links(kept)
    return {"id": link_id}


def natural_key(value: str) -> list[object]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def create_profile(name: str, email: str = "", note: str = "", status: str = "empty") -> dict:
    path = profile_dir(name)
    path.mkdir(parents=True, exist_ok=True)
    meta = read_meta(path)
    first_create = not meta
    meta.update(
        {
            "email": email if email != "" else meta.get("email", ""),
            "note": note if note != "" else meta.get("note", ""),
            "status": status or meta.get("status", "empty"),
            "updatedAt": now_ms(),
        }
    )
    if first_create:
        meta["createdAt"] = now_ms()
    write_meta(path, meta)
    return profile_record(path)


def update_profile(name: str, updates: dict) -> dict:
    path = profile_dir(name)
    if not path.exists():
        raise FileNotFoundError(name)
    meta = read_meta(path)
    for key in ("email", "note", "status"):
        if key in updates:
            meta[key] = str(updates.get(key) or "")
    meta["updatedAt"] = now_ms()
    write_meta(path, meta)
    new_name = updates.get("name")
    if new_name is None or safe_name(str(new_name)) == path.name:
        return profile_record(path)

    target = profile_dir(str(new_name))
    if target.exists():
        raise ValueError(f"Profile name already exists: {target.name}")
    cleanup_profile_locks(path.name)
    move_profile_with_retry(path, target)
    return profile_record(target)


def delete_profile(name: str) -> dict:
    path = profile_dir(name)
    if not path.exists():
        raise FileNotFoundError(name)
    cleanup_profile_locks(path.name)
    DELETED_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = DELETED_ROOT / f"{path.name}-{stamp}"
    suffix = 1
    while target.exists():
        target = DELETED_ROOT / f"{path.name}-{stamp}-{suffix}"
        suffix += 1
    move_profile_with_retry(path, target)
    return {"name": path.name, "deletedTo": str(target)}


def cleanup_profile_locks(name: str) -> None:
    terminate_login_process(name)
    terminate_profile_chrome(name)
    time.sleep(0.2)


def terminate_login_process(name: str) -> None:
    path = profile_dir(name)
    record = LOGIN_PROCS.pop(path.name, None)
    if not record:
        return
    proc = record.get("process")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    close_login_handles(record)


def close_login_handles(record: dict) -> None:
    for key in ("stdout", "stderr"):
        try:
            handle = record.get(key)
            if handle:
                handle.close()
        except Exception:
            pass


def terminate_profile_chrome(name: str) -> None:
    if os.name != "nt":
        return
    path = profile_dir(name)
    marker = f"--user-data-dir={path}".lower()
    ps_script = f"""
$marker = {json.dumps(marker)}
Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" |
  Where-Object {{ ($_.CommandLine -as [string]).ToLower().Contains($marker) }} |
  ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass


def move_profile_with_retry(path: Path, target: Path) -> None:
    last_error: Exception | None = None
    for _ in range(8):
        try:
            shutil.move(str(path), str(target))
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.35)
        except OSError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 32:
                raise
            time.sleep(0.35)
    raise RuntimeError(f"Profile is still in use; close its Chrome window and retry. Last error: {last_error}")


def codex_executable() -> str:
    if sys.platform == "darwin":
        candidates = [
            Path("/opt/homebrew/bin/codex"),
            Path("/usr/local/bin/codex"),
            Path.home() / ".npm-global/bin/codex",
            Path.home() / ".local/bin/codex",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

    candidates = [
        r"C:\Program Files\OpenAI Codex\codex.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    executable_name = "codex.exe" if os.name == "nt" else "codex"
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / executable_name
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Codex CLI was not found.")


def clean_finished_login(name: str) -> None:
    record = LOGIN_PROCS.get(name)
    if not record:
        return
    proc = record.get("process")
    if proc and proc.poll() is None:
        return
    record = LOGIN_PROCS.pop(name, None)
    if record:
        close_login_handles(record)


def parse_login_output(text: str) -> dict:
    plain = strip_ansi(text)
    url_match = re.search(r"https://auth\.openai\.com/[^\s]+", plain)
    code_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{5})\b", plain)
    mode = "device" if code_match else "web"
    return {
        "url": url_match.group(0) if url_match else "",
        "code": code_match.group(1) if code_match else "",
        "mode": mode,
        "raw": plain.strip(),
    }


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def oauth_metadata() -> dict:
    global AUTH_CONFIG
    if AUTH_CONFIG:
        return AUTH_CONFIG

    fallback = {
        "authorization_endpoint": f"{AUTH_ISSUER}/authorize",
        "token_endpoint": "https://auth0.openai.com/oauth/token",
    }
    try:
        request = urllib.request.Request(AUTH_DISCOVERY_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        AUTH_CONFIG = {
            "authorization_endpoint": payload.get("authorization_endpoint") or fallback["authorization_endpoint"],
            "token_endpoint": payload.get("token_endpoint") or fallback["token_endpoint"],
        }
    except Exception:
        AUTH_CONFIG = fallback
    return AUTH_CONFIG


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def ensure_oauth_callback_server() -> int:
    global OAUTH_CALLBACK_SERVER, OAUTH_CALLBACK_PORT
    with OAUTH_CALLBACK_LOCK:
        if OAUTH_CALLBACK_SERVER:
            return OAUTH_CALLBACK_PORT

        preferred = int(os.environ.get("PROFILE_MANAGER_AUTH_PORT") or DEFAULT_CALLBACK_PORT)
        for port in range(preferred, preferred + 50):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
            except OSError:
                continue
            OAUTH_CALLBACK_SERVER = server
            OAUTH_CALLBACK_PORT = port
            thread = threading.Thread(target=server.serve_forever, name=f"OAuthCallback:{port}", daemon=True)
            thread.start()
            return port
    raise RuntimeError("No available local OAuth callback port found.")


def callback_redirect_uri() -> str:
    return f"http://localhost:{ensure_oauth_callback_server()}/auth/callback"


def authorization_url(redirect_uri: str, state: str, challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": CODEX_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": CODEX_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "Codex Desktop",
    }
    return oauth_metadata()["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)


def remove_oauth_login_for_profile(name: str) -> None:
    with OAUTH_LOCK:
        for state, record in list(OAUTH_LOGINS.items()):
            if record.get("profile") == name:
                OAUTH_LOGINS.pop(state, None)


def oauth_login_for_profile(name: str) -> dict | None:
    cutoff = now_ms() - 30 * 60 * 1000
    with OAUTH_LOCK:
        for state, record in list(OAUTH_LOGINS.items()):
            if int(record.get("startedAt") or 0) < cutoff:
                OAUTH_LOGINS.pop(state, None)
                continue
            if record.get("profile") == name:
                return dict(record)
    return None


def start_web_oauth_login(name: str) -> dict:
    path = profile_dir(name)
    path.mkdir(parents=True, exist_ok=True)
    terminate_login_process(path.name)
    remove_oauth_login_for_profile(path.name)

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    redirect_uri = callback_redirect_uri()
    login_url = authorization_url(redirect_uri, state, challenge)
    with OAUTH_LOCK:
        OAUTH_LOGINS[state] = {
            "profile": path.name,
            "startedAt": now_ms(),
            "mode": "web",
            "status": "running",
            "state": state,
            "codeVerifier": verifier,
            "redirectUri": redirect_uri,
            "loginUrl": login_url,
            "error": "",
        }

    try:
        open_profile(path.name, login_url)
    except Exception:
        with OAUTH_LOCK:
            OAUTH_LOGINS.pop(state, None)
        raise
    return official_login_status(path.name)


def exchange_oauth_code(code: str, redirect_uri: str, verifier: str) -> dict:
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CODEX_CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        oauth_metadata()["token_endpoint"],
        data=form,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Token exchange failed: HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Token exchange failed: {exc.reason}") from exc


def save_official_auth(name: str, token_payload: dict) -> dict:
    id_token = token_payload.get("id_token") or ""
    access_token = token_payload.get("access_token") or ""
    refresh_token = token_payload.get("refresh_token") or ""
    if not id_token or not access_token:
        raise RuntimeError("Auth response did not include required tokens.")

    id_claims = decode_jwt_payload(id_token)
    access_claims = decode_jwt_payload(access_token)
    id_auth = id_claims.get("https://api.openai.com/auth") if isinstance(id_claims, dict) else {}
    access_auth = access_claims.get("https://api.openai.com/auth") if isinstance(access_claims, dict) else {}
    account_id = (
        token_payload.get("account_id")
        or (access_auth or {}).get("chatgpt_account_id")
        or (id_auth or {}).get("chatgpt_account_id")
        or ""
    )
    payload = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": id_token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "account_id": account_id,
        },
        "last_refresh": utc_now_iso(),
    }

    codex_home = profile_codex_home(name)
    codex_home.mkdir(parents=True, exist_ok=True)
    path = official_auth_path(name)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

    profile_path = profile_dir(name)
    meta = read_meta(profile_path)
    email = id_claims.get("email") or access_claims.get("email") or ""
    if email and not meta.get("email"):
        meta["email"] = email
    meta["status"] = "ready"
    meta["updatedAt"] = now_ms()
    write_meta(profile_path, meta)
    return official_auth_record(name)


def complete_oauth_callback(query: dict[str, list[str]]) -> tuple[bool, str, str]:
    state = (query.get("state") or [""])[0]
    code = (query.get("code") or [""])[0]
    upstream_error = (query.get("error_description") or query.get("error") or [""])[0]
    if not state:
        return False, "授权失败", "回调缺少 state。"

    with OAUTH_LOCK:
        record = OAUTH_LOGINS.get(state)
        if record:
            record["status"] = "exchanging"

    if not record:
        return False, "授权失败", "这个授权状态已经过期，请回到管理台重新点第二步。"
    if upstream_error:
        with OAUTH_LOCK:
            record["status"] = "error"
            record["error"] = upstream_error
        return False, "授权失败", upstream_error
    if not code:
        with OAUTH_LOCK:
            record["status"] = "error"
            record["error"] = "回调缺少授权 code。"
        return False, "授权失败", "回调缺少授权 code。"

    try:
        tokens = exchange_oauth_code(code, record["redirectUri"], record["codeVerifier"])
        auth = save_official_auth(record["profile"], tokens)
        with OAUTH_LOCK:
            OAUTH_LOGINS.pop(state, None)
        email = auth.get("email") or record["profile"]
        return True, "auth.json 已保存", f"{email} 的官方 auth.json 已保存，可以关闭这个窗口。"
    except Exception as exc:
        with OAUTH_LOCK:
            record["status"] = "error"
            record["error"] = str(exc)
        return False, "授权失败", str(exc)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "ChatGPTProfileOAuth/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_html(HTTPStatus.NOT_FOUND, "Not Found", "Unknown callback path.")
            return
        ok, title, message = complete_oauth_callback(urllib.parse.parse_qs(parsed.query))
        status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
        self.send_html(status, title, message)

    def send_html(self, status: HTTPStatus, title: str, message: str) -> None:
        color = "#15803d" if status == HTTPStatus.OK else "#b91c1c"
        body = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<body style="font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:40px;line-height:1.6;">
  <h1 style="color:{color};margin:0 0 12px;">{html.escape(title)}</h1>
  <p>{html.escape(message)}</p>
  <p>回到 ChatGPT Profile Manager 后点“查状态”或等待列表自动刷新。</p>
</body>
</html>""".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_official_login(name: str, mode: str = "web") -> dict:
    path = profile_dir(name)
    path.mkdir(parents=True, exist_ok=True)
    clean_finished_login(path.name)
    if mode not in {"web", "device"}:
        raise ValueError("Invalid login mode.")
    if mode == "web":
        return start_web_oauth_login(path.name)

    existing = LOGIN_PROCS.get(path.name)
    if existing and existing["process"].poll() is None:
        return official_login_status(path.name)

    codex_home = profile_codex_home(path.name)
    codex_home.mkdir(parents=True, exist_ok=True)
    out = codex_home / "login.out.txt"
    err = codex_home / "login.err.txt"
    out.write_text("", encoding="utf-8")
    err.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    stdout_handle = open(out, "w", encoding="utf-8")
    stderr_handle = open(err, "w", encoding="utf-8")
    args = [codex_executable(), "login"]
    if mode == "device":
        args.append("--device-auth")
    process = subprocess.Popen(
        args,
        cwd=str(WORKSPACE),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    LOGIN_PROCS[path.name] = {
        "process": process,
        "startedAt": now_ms(),
        "out": out,
        "err": err,
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "mode": mode,
    }

    # Give the CLI a moment to print the auth URL, then open it in this profile.
    for _ in range(30):
        status = official_login_status(path.name)
        if status.get("loginUrl") or status.get("code"):
            break
        time.sleep(0.1)
    try:
        status = official_login_status(path.name)
        open_profile(path.name, status.get("loginUrl") or CODEX_DEVICE_URL)
    except Exception:
        pass
    return official_login_status(path.name)


def official_login_status(name: str) -> dict:
    path = profile_dir(name)
    clean_finished_login(path.name)
    auth = official_auth_record(path.name)
    oauth_record = oauth_login_for_profile(path.name)
    if oauth_record:
        running = oauth_record.get("status") in {"running", "exchanging"}
        message = "授权页已在该账号的独立 Chrome 窗口打开。"
        if oauth_record.get("status") == "exchanging":
            message = "授权完成，正在保存 auth.json。"
        if oauth_record.get("status") == "error":
            message = "授权失败，请重新点第二步。"
        return {
            "profile": path.name,
            "running": running,
            "startedAt": oauth_record.get("startedAt"),
            "mode": "web",
            "loginUrl": oauth_record.get("loginUrl") or "",
            "deviceUrl": oauth_record.get("loginUrl") or CODEX_DEVICE_URL,
            "code": "",
            "message": message,
            "error": oauth_record.get("error") or "",
            "officialAuth": auth,
        }

    record = LOGIN_PROCS.get(path.name)
    output = ""
    error_output = ""
    running = False
    started_at = None
    mode = "web"
    if record:
        running = record["process"].poll() is None
        started_at = record.get("startedAt")
        mode = record.get("mode", "web")
        output = read_text_if_exists(record["out"])
        error_output = read_text_if_exists(record["err"])
    login_info = parse_login_output(output + "\n" + error_output)
    login_url = login_info["url"] or (CODEX_DEVICE_URL if mode == "device" else "")
    return {
        "profile": path.name,
        "running": running,
        "startedAt": started_at,
        "mode": mode,
        "loginUrl": login_url,
        "deviceUrl": login_url or CODEX_DEVICE_URL,
        "code": login_info["code"],
        "message": login_info["raw"],
        "error": strip_ansi(error_output).strip(),
        "officialAuth": auth,
    }


def stop_official_login(name: str) -> dict:
    path = profile_dir(name)
    terminate_login_process(path.name)
    remove_oauth_login_for_profile(path.name)
    return official_login_status(path.name)


def open_profile(name: str, url: str | None = None) -> dict:
    path = profile_dir(name)
    path.mkdir(parents=True, exist_ok=True)
    meta = read_meta(path)
    meta.setdefault("createdAt", now_ms())
    meta["lastOpenedAt"] = now_ms()
    meta["updatedAt"] = now_ms()
    if meta.get("status", "empty") == "empty":
        meta["status"] = "opened"
    write_meta(path, meta)

    chrome = find_chrome()
    target_url = normalize_url(url or DEFAULT_URL)
    args = [
        chrome,
        f"--user-data-dir={path}",
        "--profile-directory=Default",
        "--no-first-run",
        "--new-window",
        target_url,
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return profile_record(path)


def normalize_url(url: str) -> str:
    value = (url or DEFAULT_URL).strip()
    if not value:
        return DEFAULT_URL
    parsed = urllib.parse.urlparse(value)
    if not parsed.scheme:
        value = "https://" + value
        parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")
    return value


def next_profile_name(prefix: str = "team", padding: int = 2) -> str:
    prefix = safe_name(prefix)
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
    max_num = 0
    for record in list_profiles():
        match = pattern.match(record["name"])
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{prefix}{max_num + 1:0{max(0, padding)}d}"


def create_batch(prefix: str, start: int, count: int, padding: int, status: str = "empty") -> list[dict]:
    if count < 1:
        raise ValueError("Count must be at least 1.")
    if count > 10000:
        raise ValueError("Count is too large for one batch.")
    prefix = safe_name(prefix)
    records = []
    for idx in range(start, start + count):
        records.append(create_profile(f"{prefix}{idx:0{max(0, padding)}d}", status=status))
    return records


class Handler(BaseHTTPRequestHandler):
    server_version = "ChatGPTProfileManager/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/profiles":
                self.send_json({"profiles": list_profiles()})
                return
            if parsed.path == "/api/auth-links":
                self.send_json({"links": read_auth_links()})
                return
            if parsed.path == "/api/profiles/auth.json":
                self.send_download_json(export_all_profiles(), "chatgpt-profiles-index.json")
                return
            match = re.match(r"^/api/profiles/([^/]+)/official-login$", parsed.path)
            if match:
                name = urllib.parse.unquote(match.group(1))
                self.send_json(official_login_status(name))
                return
            match = re.match(r"^/api/profiles/([^/]+)/auth\.json$", parsed.path)
            if match:
                name = urllib.parse.unquote(match.group(1))
                path = official_auth_path(name)
                if not path.exists():
                    raise FileNotFoundError("official auth.json not found; run 官方登录 first")
                self.send_download_file(path, f"{safe_name(name)}-auth.json")
                return
            match = re.match(r"^/api/profiles/([^/]+)/profile\.json$", parsed.path)
            if match:
                name = urllib.parse.unquote(match.group(1))
                self.send_download_json(export_profile(name), f"{safe_name(name)}-profile.json")
                return
            if self.path.startswith("/api/next-name"):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                prefix = (query.get("prefix") or ["team"])[0]
                padding = int((query.get("padding") or ["2"])[0])
                self.send_json({"name": next_profile_name(prefix, padding)})
                return
            self.serve_static()
        except Exception as exc:
            self.send_error_json(exc)

    def do_POST(self) -> None:
        try:
            body = self.read_json()
            if self.path == "/api/profiles":
                record = create_profile(
                    body.get("name", ""),
                    email=body.get("email", ""),
                    note=body.get("note", ""),
                    status=body.get("status", "empty"),
                )
                self.send_json({"profile": record}, HTTPStatus.CREATED)
                return
            if self.path == "/api/auth-links":
                link = create_auth_link(body.get("label", ""), body.get("url", ""))
                self.send_json({"link": link, "links": read_auth_links()}, HTTPStatus.CREATED)
                return
            if self.path == "/api/profiles/open":
                record = open_profile(body.get("name", ""), body.get("url") or DEFAULT_URL)
                self.send_json({"profile": record})
                return
            match = re.match(r"^/api/profiles/([^/]+)/official-login$", urllib.parse.urlparse(self.path).path)
            if match:
                name = urllib.parse.unquote(match.group(1))
                self.send_json(start_official_login(name, body.get("mode", "web")), HTTPStatus.CREATED)
                return
            match = re.match(r"^/api/profiles/([^/]+)/official-login/stop$", urllib.parse.urlparse(self.path).path)
            if match:
                name = urllib.parse.unquote(match.group(1))
                self.send_json(stop_official_login(name))
                return
            if self.path == "/api/profiles/batch":
                records = create_batch(
                    body.get("prefix", "team"),
                    int(body.get("start", 1)),
                    int(body.get("count", 1)),
                    int(body.get("padding", 2)),
                    body.get("status", "empty"),
                )
                self.send_json({"profiles": records}, HTTPStatus.CREATED)
                return
            if self.path == "/api/profiles/open-next":
                name = next_profile_name(body.get("prefix", "team"), int(body.get("padding", 2)))
                record = create_profile(name, status="opened")
                record = open_profile(record["name"], body.get("url") or DEFAULT_URL)
                self.send_json({"profile": record}, HTTPStatus.CREATED)
                return
            self.send_error_json(FileNotFoundError(self.path), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_error_json(exc)

    def do_PATCH(self) -> None:
        try:
            match = re.match(r"^/api/profiles/([^/]+)$", urllib.parse.urlparse(self.path).path)
            if not match:
                self.send_error_json(FileNotFoundError(self.path), HTTPStatus.NOT_FOUND)
                return
            name = urllib.parse.unquote(match.group(1))
            record = update_profile(name, self.read_json())
            self.send_json({"profile": record})
        except Exception as exc:
            self.send_error_json(exc)

    def do_DELETE(self) -> None:
        try:
            parsed_path = urllib.parse.urlparse(self.path).path
            match = re.match(r"^/api/profiles/([^/]+)$", parsed_path)
            if match:
                name = urllib.parse.unquote(match.group(1))
                self.send_json({"deleted": delete_profile(name)})
                return
            match = re.match(r"^/api/auth-links/([^/]+)$", parsed_path)
            if match:
                link_id = urllib.parse.unquote(match.group(1))
                self.send_json({"deleted": delete_auth_link(link_id), "links": read_auth_links()})
                return
            else:
                self.send_error_json(FileNotFoundError(self.path), HTTPStatus.NOT_FOUND)
                return
        except Exception as exc:
            self.send_error_json(exc)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_download_json(self, payload: dict, filename: str) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_download_file(self, path: Path, filename: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, exc: Exception, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        if isinstance(exc, FileNotFoundError):
            status = HTTPStatus.NOT_FOUND
        elif isinstance(exc, ValueError):
            status = HTTPStatus.BAD_REQUEST
        payload = {"error": type(exc).__name__, "message": str(exc)}
        self.send_json(payload, status)

    def serve_static(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        rel = parsed.path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = (WEB_ROOT / rel).resolve()
        root = WEB_ROOT.resolve()
        if root != target and root not in target.parents:
            self.send_error_json(FileNotFoundError(rel), HTTPStatus.NOT_FOUND)
            return
        if not target.exists() or not target.is_file():
            self.send_error_json(FileNotFoundError(rel), HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8"
        if target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def pick_port(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local port found.")


def main() -> None:
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    DELETED_ROOT.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PROFILE_MANAGER_PORT") or pick_port(8765))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"ChatGPT Profile Manager ({platform.system()}): http://127.0.0.1:{port}", flush=True)
    print(f"Profile root: {PROFILE_ROOT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
