"""
graph.py — Microsoft Graph 로 SharePoint 리스트를 읽어 대시보드 레코드로 변환.

인증: delegated. MSAL device-flow 로 1회 로그인(bootstrap_login.py)하면 토큰 캐시가
Gist 에 저장되고, 서버는 그 캐시로 silent 갱신만 한다(무인).

핵심:
- Graph 의 list item 'fields' 는 컬럼 "내부 이름"을 키로 준다. 한글 표시이름과 다르므로
  먼저 컬럼 메타(내부이름→표시이름)를 읽어 레코드 키를 표시이름으로 복원한다.
- COLUMN_ALIAS 로 표시이름을 analyzer 가 기대하는 형태로 보정할 수 있다(실 컬럼 확인 후 채움).
"""

import urllib.parse

import msal
import requests

import store

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# 정적으로 사전 동의된 delegated 권한(예: Sites.Selected)을 그대로 사용.
SCOPES = ["https://graph.microsoft.com/.default"]

# 표시이름 보정: { SharePoint 실제 표시이름: analyzer 가 기대하는 이름 }
# 실제 컬럼 확인 결과 표시이름이 폼 질문 전문 그대로라 보정이 불필요했다(비워둠).
# 향후 질문 문구가 바뀌어 매칭이 깨지면 여기에 { "실제 표시이름": "기대 이름" } 추가.
COLUMN_ALIAS = {}

# Forms 가져오기로 만든 리스트의 실제 응답 컬럼은 모두 'field_N' 내부이름을 갖는다.
# 그 외(Title/ID/ContentType/_* 등)는 SharePoint 시스템 컬럼이므로 제외한다.
ANSWER_PREFIX = "field_"


# ---------------------------------------------------------------------------
# 인증
# ---------------------------------------------------------------------------
def _build_app():
    authority = f"https://login.microsoftonline.com/{store.cfg('TENANT_ID')}"
    cache = msal.SerializableTokenCache()
    cached = store.load_token_cache()
    if cached:
        cache.deserialize(cached)
    app = msal.PublicClientApplication(
        store.cfg("CLIENT_ID"), authority=authority, token_cache=cache
    )
    return app, cache


def _save_if_changed(cache):
    if cache.has_state_changed:
        store.save_token_cache(cache.serialize())


def get_token_silent(force_refresh=False):
    """저장된 계정으로 조용히 토큰을 갱신. 없으면 None(=재로그인 필요).
    force_refresh=True 면 캐시된 액세스 토큰을 무시하고 새로 발급(권한 변경 직후 유용)."""
    app, cache = _build_app()
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(SCOPES, account=accounts[0], force_refresh=force_refresh)
    _save_if_changed(cache)
    if result and "access_token" in result:
        return result["access_token"]
    return None


def login_device_flow(print_fn=print):
    """대화형 device-flow 로그인(최초 1회, 로컬). 성공 시 토큰을 Gist 에 저장."""
    app, cache = _build_app()
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError("device flow 생성 실패: " + str(flow))
    print_fn(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    _save_if_changed(cache)
    if "access_token" not in result:
        raise RuntimeError(
            "토큰 획득 실패: "
            + result.get("error", "")
            + " / "
            + result.get("error_description", "")
        )
    return result["access_token"]


# ---------------------------------------------------------------------------
# Graph 헬퍼
# ---------------------------------------------------------------------------
def _get(token, url):
    full = url if url.startswith("http") else GRAPH_BASE + url
    resp = requests.get(full, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_site_id(token):
    host = store.cfg("SHAREPOINT_SITE", "develice.sharepoint.com")
    name = store.cfg("SHAREPOINT_SITE_NAME", "khp-elicelab")
    site = _get(token, f"/sites/{host}:/sites/{name}")
    return site["id"]


def get_list_id(token, site_id, list_name):
    """리스트 GUID 를 찾는다. 우선순위: LIST_ID(GUID) > URLNAME 직접주소 > 표시이름 직접주소
    > displayName 필터 > 전체 열거. (Sites.Selected 에선 전체 열거가 막힐 수 있어 직접주소가 핵심)"""
    # 1) GUID 가 설정돼 있으면 직접 사용(가장 안정적)
    guid = (store.cfg("SHAREPOINT_LIST_ID", "") or "").strip()
    if guid:
        return _get(token, f"/sites/{site_id}/lists/{guid}")["id"]

    # 2) 경로로 직접 주소 지정 (URL 내부이름 → 표시이름 순)
    urlname = (store.cfg("SHAREPOINT_LIST_URLNAME", "") or "").strip()
    for cand in [urlname, (list_name or "").strip()]:
        if not cand:
            continue
        try:
            return _get(token, f"/sites/{site_id}/lists/{urllib.parse.quote(cand)}")["id"]
        except requests.HTTPError:
            pass

    # 3) displayName 필터
    if list_name:
        q = list_name.strip().replace("'", "''")
        data = _get(token, f"/sites/{site_id}/lists?$filter=displayName eq '{urllib.parse.quote(q)}'")
        vals = data.get("value", [])
        if vals:
            return vals[0]["id"]

    # 4) 전체 열거 후 매칭(폴백)
    data = _get(token, f"/sites/{site_id}/lists?$select=id,name,displayName&$top=200")
    for lst in data.get("value", []):
        if lst.get("displayName") == (list_name or "").strip() or lst.get("name") in (urlname, list_name):
            return lst["id"]
    raise RuntimeError(
        f"리스트를 찾지 못했습니다 (name={list_name!r}, urlname={urlname!r})."
    )


def get_column_map(token, site_id, list_id):
    """{내부이름: 표시이름} 매핑을 반환."""
    data = _get(token, f"/sites/{site_id}/lists/{list_id}/columns?$select=name,displayName,readOnly,hidden")
    cmap = {}
    for col in data.get("value", []):
        name = col.get("name")
        disp = col.get("displayName") or name
        if name:
            cmap[name] = disp
    return cmap


def get_items(token, site_id, list_id, colmap):
    """리스트 아이템 전체를 페이지네이션으로 읽어 레코드 목록으로 변환."""
    from app import RID_KEY  # 예약 키 재사용(순환 import 안전: 함수 내부)

    records = []
    url = f"/sites/{site_id}/lists/{list_id}/items?expand=fields&$top=200"
    while url:
        page = _get(token, url)
        for item in page.get("value", []):
            fields = item.get("fields", {}) or {}
            rec = {}
            for key, val in fields.items():
                if not key.startswith(ANSWER_PREFIX):  # 시스템 컬럼 제외, 폼 답변만
                    continue
                disp = colmap.get(key, key)
                disp = COLUMN_ALIAS.get(disp, disp)
                rec[disp] = val
            rec[RID_KEY] = str(item.get("id"))
            records.append(rec)
        url = page.get("@odata.nextLink")
    return records


def fetch_records():
    """전체 파이프라인: 토큰→사이트→리스트→컬럼맵→아이템 → (records, filename)."""
    token = get_token_silent()
    if not token:
        raise RuntimeError("로그인 토큰이 없습니다. bootstrap_login.py 로 1회 로그인하세요.")
    site_id = get_site_id(token)
    list_name = store.cfg("SHAREPOINT_LIST_NAME", store.cfg("SHEET_NAME", ""))
    list_id = get_list_id(token, site_id, list_name)
    colmap = get_column_map(token, site_id, list_id)
    records = get_items(token, site_id, list_id, colmap)
    return records, list_name


def inspect_columns():
    """진단용: 실제 컬럼(내부이름/표시이름)과 샘플 1건을 반환."""
    token = get_token_silent()
    if not token:
        raise RuntimeError("로그인 토큰이 없습니다. bootstrap_login.py 로 1회 로그인하세요.")
    site_id = get_site_id(token)
    list_name = store.cfg("SHAREPOINT_LIST_NAME", store.cfg("SHEET_NAME", ""))
    list_id = get_list_id(token, site_id, list_name)
    colmap = get_column_map(token, site_id, list_id)
    sample = _get(
        token,
        f"/sites/{site_id}/lists/{list_id}/items?expand=fields&$top=1",
    ).get("value", [])
    sample_fields = sample[0].get("fields", {}) if sample else {}
    return {"list_name": list_name, "list_id": list_id,
            "columns": colmap, "sample_fields": sample_fields}
