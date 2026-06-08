"""
app.py — 엘리스랩 만족도 대시보드 (FastAPI)

실행:
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
    → http://127.0.0.1:8000

설계:
- 템플릿 엔진 없이 정적 HTML 직접 서빙.
- 업로드 데이터는 "브라우저 세션별"로 인메모리 보관(SESSIONS) → 팀원끼리 데이터가 섞이지 않음.
  쿠키(dash_sid)로 세션을 구분한다. 서버 재시작 시 데이터는 초기화(재업로드 필요).
- 단일 인스턴스/단일 워커(--workers 1) 전제. 키는 환경변수(ANTHROPIC_API_KEY)로 주입.
"""

import io
import os
import secrets
import time

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import ai_keywords
import analyzer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "dashboard.html")

app = FastAPI(title="엘리스랩 만족도 대시보드")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---- 브라우저 세션별 인메모리 상태 ----
SESSION_COOKIE = "dash_sid"
MAX_SESSIONS = 100           # 메모리 보호용 상한(오래된 세션부터 제거)
SESSIONS = {}                # sid -> {"df", "filename", "ai", "ts"}


def _ensure_sid(request: Request, response: Response) -> str:
    """요청 쿠키에서 세션 id 를 읽고, 없으면 새로 발급해 응답 쿠키에 심는다."""
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = secrets.token_urlsafe(16)
        response.set_cookie(
            SESSION_COOKIE, sid,
            max_age=60 * 60 * 24 * 7, httponly=True, samesite="lax",
        )
    return sid


def _bucket(sid: str) -> dict:
    b = SESSIONS.get(sid)
    if b is None:
        b = {"df": None, "filename": None, "ai": None, "ts": time.time()}
        SESSIONS[sid] = b
        if len(SESSIONS) > MAX_SESSIONS:
            oldest = sorted(SESSIONS, key=lambda k: SESSIONS[k]["ts"])[: len(SESSIONS) - MAX_SESSIONS]
            for k in oldest:
                SESSIONS.pop(k, None)
    b["ts"] = time.time()
    return b


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()
    resp = HTMLResponse(html, headers={"Cache-Control": "no-store"})
    if not request.cookies.get(SESSION_COOKIE):
        resp.set_cookie(
            SESSION_COOKIE, secrets.token_urlsafe(16),
            max_age=60 * 60 * 24 * 7, httponly=True, samesite="lax",
        )
    return resp


@app.get("/health")
def health():
    """keep-alive 핑 전용 — 세션/상태를 건드리지 않는 초경량 응답."""
    return {"ok": True}


@app.get("/api/status")
def status(request: Request, response: Response):
    sid = _ensure_sid(request, response)
    b = _bucket(sid)
    if b["df"] is None:
        return {"has_data": False, "filename": None, "courses": []}
    return {
        "has_data": True,
        "filename": b["filename"],
        "rows": int(len(b["df"])),
        "courses": analyzer.get_courses(b["df"]),
    }


@app.post("/upload")
async def upload(request: Request, response: Response, file: UploadFile = File(...)):
    sid = _ensure_sid(request, response)
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Excel 파일(.xlsx/.xls)만 업로드할 수 있습니다.")
    content = await file.read()
    try:
        df = analyzer.load_dataframe(io.BytesIO(content))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"파일 파싱 실패: {e}")

    if df.empty:
        raise HTTPException(400, "데이터가 비어 있습니다.")

    b = _bucket(sid)
    b["df"] = df
    b["filename"] = file.filename
    # 주관식 키워드 분석은 업로드 시 1회만 호출하고 결과를 캐싱한다.
    b["ai"] = ai_keywords.analyze_subjective(analyzer.get_subjective_responses(df))
    return {
        "ok": True,
        "filename": file.filename,
        "rows": int(len(df)),
        "courses": analyzer.get_courses(df),
    }


@app.get("/api/dashboard")
def dashboard(request: Request, response: Response, course: str = "전체"):
    sid = _ensure_sid(request, response)
    b = _bucket(sid)
    if b["df"] is None:
        raise HTTPException(404, "업로드된 데이터가 없습니다.")
    data = analyzer.analyze(b["df"], course=course, filename=b["filename"])
    data["ai_analysis"] = b.get("ai")  # 필터와 무관한 전체 분석(캐시)
    return data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
