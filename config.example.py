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
GITHUB_GIST_ID = "f7fea727f3b29fa90167c89f0a48abf6"
GITHUB_TOKEN = ""

# Claude API (주관식 키워드 분석). 키가 비어 있으면 단어 빈도 분석으로 자동 폴백.
ANTHROPIC_API_KEY = ""
CLAUDE_MODEL = "claude-sonnet-4-20250514"
