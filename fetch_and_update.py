"""
fetch_and_update.py

Microsoft 365 계정으로 SharePoint에 있는 Excel 파일을 Microsoft Graph API로
읽어서, 시트 데이터를 JSON으로 변환한 뒤 GitHub Gist에 업데이트하는 스크립트.

인증: MSAL device code flow (브라우저에서 코드 입력 방식).

사용법:
    pip install -r requirements.txt
    python fetch_and_update.py
"""

import json
import sys
import urllib.parse

import msal
import requests

import config


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# device code flow 는 public client 이므로 delegated 권한 scope 를 사용한다.
SCOPES = ["Sites.Read.All", "Files.Read.All"]
TOKEN_CACHE_FILE = "token_cache.bin"


# ---------------------------------------------------------------------------
# 1. 인증 (MSAL device code flow)
# ---------------------------------------------------------------------------
def get_access_token():
    """device code flow 로 Microsoft Graph access token 을 획득한다."""
    authority = f"https://login.microsoftonline.com/{config.TENANT_ID}"

    # 토큰 캐시: 한 번 로그인하면 재실행 시 silent 로 재사용한다.
    cache = msal.SerializableTokenCache()
    try:
        with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
            cache.deserialize(f.read())
    except FileNotFoundError:
        pass

    app = msal.PublicClientApplication(
        config.CLIENT_ID,
        authority=authority,
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        # 캐시에 계정이 있으면 조용히 토큰 갱신을 시도한다.
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(
                "device flow 생성 실패: " + json.dumps(flow, ensure_ascii=False)
            )
        # 사용자에게 표시되는 안내 메시지 (URL + 코드)
        print(flow["message"])
        sys.stdout.flush()
        result = app.acquire_token_by_device_flow(flow)

    # 변경된 캐시 저장
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(cache.serialize())

    if "access_token" not in result:
        raise RuntimeError(
            "토큰 획득 실패: "
            + result.get("error", "")
            + " / "
            + result.get("error_description", "")
        )
    return result["access_token"]


# ---------------------------------------------------------------------------
# 2. SharePoint / Graph 헬퍼
# ---------------------------------------------------------------------------
def graph_get(token, url):
    """Graph GET 요청 후 JSON 반환 (절대 URL 또는 GRAPH_BASE 기준 상대 경로)."""
    if url.startswith("http"):
        full = url
    else:
        full = GRAPH_BASE + url
    resp = requests.get(full, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


def get_site_id(token):
    """호스트명 + 사이트 이름으로 SharePoint site id 를 조회한다."""
    path = f"/sites/{config.SHAREPOINT_SITE}:/sites/{config.SHAREPOINT_SITE_NAME}"
    site = graph_get(token, path)
    return site["id"]


def find_excel_drive_item(token, site_id):
    """사이트 기본 문서 라이브러리에서 Excel 파일의 drive item 을 찾는다."""
    # 파일 이름으로 검색
    query = urllib.parse.quote(config.EXCEL_FILE_NAME)
    search = graph_get(
        token,
        f"/sites/{site_id}/drive/root/search(q='{query}')",
    )
    for item in search.get("value", []):
        if item.get("name") == config.EXCEL_FILE_NAME:
            return item["id"]

    raise RuntimeError(
        f"'{config.EXCEL_FILE_NAME}' 파일을 사이트 문서함에서 찾지 못했습니다."
    )


def fetch_sheet_rows(token, site_id, item_id):
    """워크북 시트의 usedRange 를 읽어 2차원 값 배열을 반환한다."""
    sheet = urllib.parse.quote(config.SHEET_NAME)
    used = graph_get(
        token,
        f"/sites/{site_id}/drive/items/{item_id}/workbook"
        f"/worksheets('{sheet}')/usedRange",
    )
    return used.get("values", [])


# ---------------------------------------------------------------------------
# 3. 데이터 변환
# ---------------------------------------------------------------------------
def rows_to_records(rows):
    """첫 행을 헤더로 사용하여 [{header: value, ...}, ...] 형태로 변환한다."""
    if not rows:
        return []
    header = [str(h).strip() for h in rows[0]]
    records = []
    for row in rows[1:]:
        # 완전히 빈 행은 건너뛴다.
        if all(cell in (None, "") for cell in row):
            continue
        record = {}
        for i, key in enumerate(header):
            record[key] = row[i] if i < len(row) else None
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# 4. GitHub Gist 업데이트
# ---------------------------------------------------------------------------
def update_gist(records):
    """변환된 레코드를 JSON 으로 직렬화하여 Gist 파일을 갱신한다."""
    payload = {
        "files": {
            "data.json": {
                "content": json.dumps(records, ensure_ascii=False, indent=2)
            }
        }
    }
    resp = requests.patch(
        f"https://api.github.com/gists/{config.GITHUB_GIST_ID}",
        headers={
            "Authorization": f"token {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    print("[1/4] Microsoft 365 인증 중...")
    token = get_access_token()

    print("[2/4] SharePoint 사이트 / 파일 조회 중...")
    site_id = get_site_id(token)
    item_id = find_excel_drive_item(token, site_id)

    print("[3/4] Excel 시트 데이터 읽는 중...")
    rows = fetch_sheet_rows(token, site_id, item_id)
    records = rows_to_records(rows)
    print(f"      → {len(records)}개 레코드 추출")

    print("[4/4] GitHub Gist 업데이트 중...")
    result = update_gist(records)
    print(f"      → 완료: {result.get('html_url', '')}")


if __name__ == "__main__":
    main()
