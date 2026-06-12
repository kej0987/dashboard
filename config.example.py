# config.py 템플릿.
# 이 파일을 config.py 로 복사한 뒤 아래 값들을 채워서 사용하세요.
#   - Azure 앱 등록: TENANT_ID / CLIENT_ID / CLIENT_SECRET
#   - GitHub: GITHUB_TOKEN (gist scope)
# config.py 는 .gitignore 에 등록되어 있어 커밋되지 않습니다.

TENANT_ID = ""
CLIENT_ID = ""
CLIENT_SECRET = ""
SHAREPOINT_SITE = "develice.sharepoint.com"
SHAREPOINT_SITE_NAME = "khp-elicelab"
EXCEL_FILE_NAME = "[엘리스랩 부산센터] 2026년도 훈련비과정 만족도 조사 1.xlsx"
SHEET_NAME = "[엘리스랩 부산센터] 2026년도 훈련비과정 만족도 조사1"
# SharePoint 리스트 식별 (우선순위: LIST_ID(GUID) > URLNAME > NAME)
SHAREPOINT_LIST_NAME = "[엘리스랩 부산센터] 2026년도 훈련비과정 만족도 조사1"  # 표시이름
SHAREPOINT_LIST_URLNAME = "2026 1"   # URL 내부이름
SHAREPOINT_LIST_ID = ""              # GUID(가장 안정적). inspect_list.py 가 알려줌
# 주의: Gist 에 데이터 + 토큰 캐시(refresh token)가 저장되므로 ID 를 커밋하지 말 것.
# 실제 값은 환경변수(GITHUB_GIST_ID) 또는 로컬 config.py 에만 둔다.
GITHUB_GIST_ID = ""
GITHUB_TOKEN = ""

# Power Automate webhook 인증용 공유 시크릿(임의 문자열). 앱과 Flow 에 동일 값 사용.
WEBHOOK_SECRET = ""

# Claude API (주관식 키워드 분석). 키가 비어 있으면 단어 빈도 분석으로 자동 폴백.
ANTHROPIC_API_KEY = ""
CLAUDE_MODEL = "claude-sonnet-4-20250514"
