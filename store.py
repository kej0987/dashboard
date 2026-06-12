"""
store.py — Gist 기반 영속 저장소.

용도 2가지:
1) 대시보드 데이터 캐시(data.json) — 콜드스타트 시 즉시 표시 + Graph 장애 대비.
2) MSAL 토큰 캐시(token_cache.json) — delegated 로그인 토큰을 Render 재배포에도 유지.

data.json 스키마:
    { "filename": str, "updated_at": float, "rows": int,
      "records": [ { "<표시이름 헤더>": <값>, ... }, ... ] }

인증: 환경변수 GITHUB_TOKEN / GITHUB_GIST_ID (없으면 config.py 폴백).
"""

import json
import os

import requests

try:
    import config
except ModuleNotFoundError:
    config = None


GITHUB_API = "https://api.github.com"
DATA_FILE = "data.json"
TOKEN_FILE = "token_cache.json"
TIMEOUT = 20


def cfg(name, default=""):
    """환경변수 우선 → config.py → default."""
    val = os.environ.get(name)
    if val:
        return val
    if config is not None:
        return getattr(config, name, default)
    return default


def _gist_id():
    return (cfg("GITHUB_GIST_ID", "") or "").strip()


def _token():
    return (cfg("GITHUB_TOKEN", "") or "").strip()


def _headers():
    return {
        "Authorization": f"token {_token()}",
        "Accept": "application/vnd.github+json",
    }


# ---------------------------------------------------------------------------
# 범용 Gist 파일 입출력
# ---------------------------------------------------------------------------
def read_gist_file(filename):
    """Gist 내 특정 파일의 텍스트 내용을 반환. 없거나 실패하면 None."""
    gid, tok = _gist_id(), _token()
    if not gid or not tok:
        return None
    try:
        resp = requests.get(f"{GITHUB_API}/gists/{gid}", headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        files = resp.json().get("files", {})
        return (files.get(filename) or {}).get("content")
    except requests.RequestException:
        return None


def write_gist_file(filename, content):
    """Gist 내 특정 파일을 갱신(없으면 생성). 성공 시 True."""
    gid, tok = _gist_id(), _token()
    if not gid or not tok:
        return False
    body = {"files": {filename: {"content": content}}}
    try:
        resp = requests.patch(
            f"{GITHUB_API}/gists/{gid}", headers=_headers(), json=body, timeout=TIMEOUT
        )
        resp.raise_for_status()
    except requests.RequestException:
        return False
    return True


# ---------------------------------------------------------------------------
# 대시보드 데이터 캐시
# ---------------------------------------------------------------------------
def load_payload():
    """data.json 을 dict 로 반환. 없으면 None."""
    content = read_gist_file(DATA_FILE)
    if not content:
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if isinstance(data, list):  # 구버전 호환(레코드 리스트 그 자체)
        return {"filename": "survey.xlsx", "updated_at": 0, "rows": len(data), "records": data}
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data
    return None


def save_payload(records, filename, updated_at):
    """records 를 data.json 으로 저장. 성공 시 True."""
    payload = {
        "filename": filename or "survey.xlsx",
        "updated_at": updated_at,
        "rows": len(records),
        "records": records,
    }
    return write_gist_file(DATA_FILE, json.dumps(payload, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# MSAL 토큰 캐시 (delegated 로그인 유지)
# ---------------------------------------------------------------------------
def load_token_cache():
    """Gist 의 token_cache.json 내용을 반환(MSAL serialize 문자열). 없으면 None."""
    return read_gist_file(TOKEN_FILE)


def save_token_cache(serialized):
    """MSAL 토큰 캐시 직렬화 문자열을 Gist 에 저장."""
    return write_gist_file(TOKEN_FILE, serialized)
