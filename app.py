"""
app.py — 엘리스랩 만족도 대시보드 (FastAPI)

실행:
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
    → http://127.0.0.1:8000

설계 (자동화 P2 방식):
- 데이터는 "전역 공유 상태"(STATE) 로 보관한다 → 모든 팀원이 같은 화면을 본다.
- 응답은 Microsoft Forms 커넥터(Power Automate)가 제출 즉시 /webhook/forms 로
  1건씩 보낸다. 응답ID 기준 upsert(by_id) 라서 재시도해도 중복되지 않는다.
- 영속성: Render 무료플랜은 재시작 시 메모리가 초기화되므로 GitHub Gist(store.py)에
  누적 저장하고, 콜드스타트 시 복원한다.
- analyzer 는 "Excel 헤더(질문 전문)" 를 키워드로 매칭하므로, 레코드의 키를
  질문 전문 그대로 넣으면 분석 로직은 수정 없이 동작한다.
- 단일 인스턴스/단일 워커(--workers 1) 전제. 비밀값은 환경변수로 주입.
"""

import hashlib
import io
import json
import os
import threading
import time

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import ai_keywords
import analyzer
import graph
import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "dashboard.html")

# 레코드에 응답ID 를 심어두는 예약 키(분석 시 제거). 헤더와 충돌하지 않게 언더스코어.
RID_KEY = "_response_id"

app = FastAPI(title="엘리스랩 만족도 대시보드")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---- 전역 공유 상태 ----
_LOCK = threading.Lock()        # STATE 변경 보호
_FETCH_LOCK = threading.Lock()  # Graph 동시 갱신 1개로 제한
GRAPH_TTL = 20                  # 초: 이 간격마다 SharePoint 를 다시 읽음
STATE = {
    "by_id": {},        # response_id -> record(dict, RID_KEY 포함)
    "df": None,         # 분석용 DataFrame (캐시)
    "ai": None,         # 주관식 키워드 분석 결과 (캐시)
    "filename": None,
    "version": 0,       # 데이터가 실제로 바뀔 때만 +1 (프론트 폴링이 변경 감지)
    "sig": None,        # 현재 데이터의 내용 서명(변경 감지용)
    "updated_at": 0,
    "last_fetch": 0,    # 마지막 Graph 조회 시각
    "loaded": False,    # Gist 콜드스타트 로드 완료 여부
}


def _signature(records):
    """레코드 내용의 서명(해시). 내용이 바뀌면 값이 바뀐다."""
    blob = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def _build_df(records):
    """레코드 목록 → 분석용 DataFrame. RID_KEY 는 제외한다."""
    import pandas as pd

    clean = [{k: v for k, v in r.items() if k != RID_KEY} for r in records]
    df = pd.DataFrame(clean)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _recompute_locked():
    """STATE['by_id'] 로부터 df/ai 를 다시 계산. 내용이 바뀐 경우에만 version 증가.
    (_LOCK 보유 상태에서 호출)"""
    records = list(STATE["by_id"].values())
    sig = _signature(records)
    if sig == STATE["sig"]:
        return  # 변경 없음 → 재계산/버전증가 생략(불필요한 AI 호출 방지)
    STATE["sig"] = sig
    if not records:
        STATE["df"] = None
        STATE["ai"] = None
    else:
        df = _build_df(records)
        STATE["df"] = df
        STATE["ai"] = ai_keywords.analyze_subjective(analyzer.get_subjective_responses(df))
    STATE["version"] += 1
    STATE["updated_at"] = time.time()


def _persist_locked():
    """현재 상태를 Gist 에 저장(베스트 에포트). 실패해도 서비스는 계속된다."""
    records = list(STATE["by_id"].values())
    store.save_payload(records, STATE["filename"], STATE["updated_at"])


def _ensure_loaded():
    """첫 요청 시 Gist 에서 1회 복원한다."""
    if STATE["loaded"]:
        return
    with _LOCK:
        if STATE["loaded"]:
            return
        payload = store.load_payload()
        if payload and payload.get("records"):
            by_id = {}
            for i, rec in enumerate(payload["records"]):
                rid = str(rec.get(RID_KEY) or f"row-{i}")
                rec[RID_KEY] = rid
                by_id[rid] = rec
            STATE["by_id"] = by_id
            STATE["filename"] = payload.get("filename")
            _recompute_locked()
        STATE["loaded"] = True


def _refresh_from_graph():
    """SharePoint 리스트를 Graph 로 읽어 STATE 를 갱신한다(네트워크는 _LOCK 밖에서)."""
    records, list_name = graph.fetch_records()  # 느릴 수 있음 → 잠금 밖에서 수행
    by_id = {}
    for i, rec in enumerate(records):
        rid = str(rec.get(RID_KEY) or f"row-{i}")
        rec[RID_KEY] = rid
        by_id[rid] = rec
    with _LOCK:
        prev = STATE["version"]
        STATE["by_id"] = by_id
        if list_name:
            STATE["filename"] = list_name
        _recompute_locked()
        if STATE["version"] != prev:      # 실제 변경이 있을 때만 Gist 캐시 갱신
            _persist_locked()


def _ensure_fresh():
    """콜드스타트 로드 + TTL 경과 시 SharePoint 재조회. 실패해도 캐시를 계속 서빙."""
    _ensure_loaded()
    if time.time() - STATE["last_fetch"] < GRAPH_TTL:
        return
    if not _FETCH_LOCK.acquire(blocking=False):
        return  # 다른 요청이 이미 갱신 중 → 캐시로 응답
    try:
        STATE["last_fetch"] = time.time()  # 실패해도 TTL 동안 재시도 안 함(쿨다운)
        _refresh_from_graph()
    except Exception:  # noqa: BLE001 — 토큰만료/네트워크 등은 캐시로 폴백
        pass
    finally:
        _FETCH_LOCK.release()


@app.on_event("startup")
def _startup():
    # 콜드스타트 시 Gist 캐시 복원 (실패해도 무시 — 첫 Graph 조회로 채워진다)
    try:
        _ensure_loaded()
    except Exception:  # noqa: BLE001
        STATE["loaded"] = True


# ---------------------------------------------------------------------------
# 페이지 / 헬스
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    """keep-alive 핑 전용 — 상태를 건드리지 않는 초경량 응답."""
    return {"ok": True}


# ---------------------------------------------------------------------------
# 상태 / 대시보드 조회 (전역)
# ---------------------------------------------------------------------------
@app.get("/api/status")
def status():
    _ensure_fresh()
    if STATE["df"] is None:
        return {"has_data": False, "filename": None, "courses": [], "version": STATE["version"]}
    return {
        "has_data": True,
        "filename": STATE["filename"],
        "rows": int(len(STATE["df"])),
        "courses": analyzer.get_courses(STATE["df"]),
        "version": STATE["version"],          # 프론트 폴링이 이 값 변화를 감지해 재로드
        "updated_at": STATE["updated_at"],
    }


@app.get("/api/dashboard")
def dashboard(course: str = "전체"):
    _ensure_fresh()
    if STATE["df"] is None:
        raise HTTPException(404, "수집된 데이터가 없습니다.")
    data = analyzer.analyze(STATE["df"], course=course, filename=STATE["filename"])
    data["ai_analysis"] = STATE["ai"]
    data["version"] = STATE["version"]
    return data


# ---------------------------------------------------------------------------
# Webhook (Power Automate / Microsoft Forms 커넥터)
# ---------------------------------------------------------------------------
def _check_secret(request: Request):
    expected = (store.cfg("WEBHOOK_SECRET", "") or "").strip()
    if not expected:
        raise HTTPException(500, "서버에 WEBHOOK_SECRET 이 설정되지 않았습니다.")
    got = request.headers.get("x-webhook-secret", "")
    if got != expected:
        raise HTTPException(401, "인증 실패: webhook 시크릿 불일치.")


@app.post("/webhook/forms")
async def webhook_forms(request: Request):
    """
    Power Automate 가 새 응답 제출 시 호출.

    헤더:  X-Webhook-Secret: <WEBHOOK_SECRET>
    본문(둘 중 하나):
      1) 응답 1건 upsert:
         { "id": "<응답ID>", "filename": "<선택>",
           "record": { "<질문 전문>": <답>, ... } }
      2) 전체 교체(복구/일괄):
         { "records": [ { "<질문 전문>": <답>, ... }, ... ], "filename": "<선택>" }
    """
    _check_secret(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "JSON 본문을 파싱할 수 없습니다.")

    if not isinstance(body, dict):
        raise HTTPException(400, "본문은 JSON 객체여야 합니다.")

    with _LOCK:
        # --- 1) 단건 upsert ---
        if isinstance(body.get("record"), dict):
            rid = str(body.get("id") or "").strip()
            if not rid:
                # 응답ID 가 없으면 안전하게 자동 증가 키 부여(중복 제거는 불가)
                rid = f"auto-{len(STATE['by_id']) + 1}-{int(time.time())}"
            rec = dict(body["record"])
            rec[RID_KEY] = rid
            STATE["by_id"][rid] = rec
            if body.get("filename"):
                STATE["filename"] = str(body["filename"])
            mode, count = "upsert", 1

        # --- 2) 전체 교체 ---
        elif isinstance(body.get("records"), list):
            by_id = {}
            for i, raw in enumerate(body["records"]):
                if not isinstance(raw, dict):
                    continue
                rec = dict(raw)
                rid = str(rec.get(RID_KEY) or rec.get("id") or f"row-{i}")
                rec[RID_KEY] = rid
                by_id[rid] = rec
            STATE["by_id"] = by_id
            if body.get("filename"):
                STATE["filename"] = str(body["filename"])
            mode, count = "replace", len(by_id)

        else:
            raise HTTPException(400, "본문에 'record' 또는 'records' 가 필요합니다.")

        if STATE["filename"] is None:
            STATE["filename"] = "Microsoft Forms 응답"
        _recompute_locked()
        _persist_locked()
        total = len(STATE["by_id"])
        version = STATE["version"]

    return {"ok": True, "mode": mode, "received": count, "total": total, "version": version}


# ---------------------------------------------------------------------------
# 수동 업로드 (백업/복구용) — 전역 상태 전체 교체
# ---------------------------------------------------------------------------
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Excel 파일(.xlsx/.xls)만 업로드할 수 있습니다.")
    content = await file.read()
    try:
        df = analyzer.load_dataframe(io.BytesIO(content))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"파일 파싱 실패: {e}")
    if df.empty:
        raise HTTPException(400, "데이터가 비어 있습니다.")

    # df → 레코드(헤더=키). 'ID' 컬럼이 있으면 응답ID 로, 없으면 행 번호로 키를 만든다.
    id_col = "ID" if "ID" in df.columns else None
    records = df.to_dict(orient="records")
    by_id = {}
    for i, rec in enumerate(records):
        rid = str(rec.get(id_col)) if id_col else f"row-{i}"
        rec[RID_KEY] = rid
        by_id[rid] = rec

    with _LOCK:
        STATE["by_id"] = by_id
        STATE["filename"] = file.filename
        _recompute_locked()
        _persist_locked()
        rows = int(len(STATE["df"])) if STATE["df"] is not None else 0
        courses = analyzer.get_courses(STATE["df"]) if STATE["df"] is not None else []

    return {"ok": True, "filename": file.filename, "rows": rows, "courses": courses}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
