"""
로컬 end-to-end 테스트 (실제 Gist 네트워크 호출 없음).

store.load_payload / save_payload 를 메모리 스텁으로 교체해
/webhook/forms upsert → /api/status version 증가 → /api/dashboard 반영을 검증한다.

실행: venv/Scripts/python.exe test_webhook_flow.py
"""
import os

os.environ["WEBHOOK_SECRET"] = "local-test-secret"

import store

# --- Gist 를 메모리로 대체 (네트워크/실데이터 보호), survey 별로 분리 ---
_MEM = {"training": None, "support": None}
store.load_payload = lambda survey="training": _MEM[survey]
def _save(records, filename, updated_at, survey="training"):
    _MEM[survey] = {"filename": filename, "updated_at": updated_at,
                     "rows": len(records), "records": records}
    return True
store.save_payload = _save
# 토큰 캐시 읽기/쓰기도 네트워크 차단
store.load_token_cache = lambda: None
store.save_token_cache = lambda s: True

# Graph 비활성(부트스트랩 전 상태 모사) → /api/* 의 자동 갱신은 캐시로 폴백
import graph
graph.get_token_silent = lambda: None

# 로컬 config.py 에 실제 ANTHROPIC_API_KEY 가 있어도 테스트는 항상 규칙기반 경로로
# 고정한다(결정적 결과 + 실제 API 호출/비용 방지).
import ai_keywords
_orig_cfg = ai_keywords._cfg
ai_keywords._cfg = lambda name, default="": "" if name == "ANTHROPIC_API_KEY" else _orig_cfg(name, default)

from fastapi.testclient import TestClient
import app as appmod

client = TestClient(appmod.app)
H = {"X-Webhook-Secret": "local-test-secret"}

Q_COURSE = "수강한 교육을 선택해 주세요"
Q_DIFF = "교육 내용의 난이도와 구성이 적절했다"
Q_INSTR = "강사의 전문성이 충분했다"
Q_APPLY = "배운 내용을 실무에 적용이 가능하다고 생각한다"
Q_SUBJ = "교육에서 도움이 된 점과 개선할 점을 자유롭게 적어주세요"


def record(rid, course, diff, instr, apply, subj):
    return {"id": rid, "filename": "엘리스랩 만족도 조사",
            "record": {Q_COURSE: course, Q_DIFF: diff, Q_INSTR: instr,
                       Q_APPLY: apply, Q_SUBJ: subj}}


def main():
    # 0) 빈 상태
    s = client.get("/api/status").json()
    assert s["has_data"] is False, s
    assert client.get("/api/dashboard").status_code == 404
    v0 = s["version"]
    print(f"[0] empty OK (version={v0})")

    # 1) 잘못된 시크릿 거부
    r = client.post("/webhook/forms", json=record("r1", "파이썬", 5, 5, 4, "좋았어요"))
    assert r.status_code == 401, r.text
    print("[1] bad secret rejected OK")

    # 2) 응답 1건 upsert
    r = client.post("/webhook/forms", headers=H,
                    json=record("r1", "파이썬 기초", 5, 5, 4, "실습이 도움이 되었어요"))
    j = r.json()
    assert r.status_code == 200 and j["mode"] == "upsert" and j["total"] == 1, j
    s = client.get("/api/status").json()
    assert s["has_data"] and s["rows"] == 1 and s["version"] > v0, s
    print(f"[2] upsert r1 OK (rows={s['rows']}, version={s['version']})")

    # 3) 두 번째 응답
    client.post("/webhook/forms", headers=H,
                json=record("r2", "데이터 분석", 4, 5, 5, "강사님이 친절했지만 시간이 부족했어요"))
    s = client.get("/api/status").json()
    assert s["rows"] == 2, s
    print(f"[3] upsert r2 OK (rows={s['rows']}, courses={s['courses']})")

    # 4) 같은 id 재전송(재시도) → 중복 없이 덮어쓰기
    client.post("/webhook/forms", headers=H,
                json=record("r1", "파이썬 기초", 3, 3, 3, "수정된 응답"))
    s = client.get("/api/status").json()
    assert s["rows"] == 2, f"중복 발생! rows={s['rows']}"
    print(f"[4] dedup OK (재전송해도 rows={s['rows']})")

    # 5) 대시보드 분석 결과 확인
    d = client.get("/api/dashboard?course=전체").json()
    assert d["kpi"]["respondents"] == 2, d["kpi"]
    assert d["kpi"]["overall"] > 0, d["kpi"]
    print(f"[5] dashboard OK (KPI overall={d['kpi']['overall']}, "
          f"강사={d['kpi']['instructor']}, 강좌수={d['kpi']['course_count']})")

    # 6) 강좌 필터 — 필터 시에만 주관식 원본 응답이 채워진다(프론트가 이 값으로 노출여부 결정)
    d2 = client.get("/api/dashboard?course=데이터 분석").json()
    assert d2["kpi"]["respondents"] == 1, d2["kpi"]
    assert d2["subjective_responses"] == ["강사님이 친절했지만 시간이 부족했어요"], d2["subjective_responses"]
    print(f"[6] course filter OK (데이터 분석 respondents={d2['kpi']['respondents']}, "
          f"원본응답={d2['subjective_responses']})")

    # 6-1) 종합 분석 요약 — API 키 없는 테스트 환경이므로 규칙기반(rule) 폴백이어야 함
    assert d["overview"] and d["overview"]["engine"] == "rule", d.get("overview")
    assert d["overview"]["summary"], d["overview"]
    print(f"[6-1] overview(rule) OK: {d['overview']['summary'][:40]}...")

    # 7) 영속 저장 확인(스텁 메모리)
    assert _MEM["training"] and _MEM["training"]["rows"] == 2, _MEM["training"]
    rids = {r[appmod.RID_KEY] for r in _MEM["training"]["records"]}
    assert rids == {"r1", "r2"}, rids
    print(f"[7] persist OK (저장된 응답ID={rids})")

    # 8) 지원비과정 탭 — 훈련비와 완전히 독립된 상태/문항 매핑인지 확인.
    #    컬럼명은 실제 SharePoint 표시이름 그대로 사용한다(Forms 섹션이 앞에 "카테고리."를
    #    붙이고 끝에 "."을 붙인다 — inspect_list.py support 로 직접 확인한 실제 형태).
    support_record = {
        "id": "s1", "filename": "지원비과정 만족도 조사",
        "record": {
            "수강하신 교육을 선택해 주세요": "AI 활용 실무",
            " 교육 만족도.교육 내용이 참여 목적과 잘 부합했다.": 5,
            " 교육 만족도.교육 난이도가 적절했다.": 4,
            " 교육 만족도.이론/실습 구성이 적절했다.": 5,
            " 교육 만족도.실습 및 교육 자료가 학습에 도움이 되었다.": 4,
            " 교육 만족도.교육 시간이 내용을 학습하기에 적절했다.": 4,
            "강사 만족도.교육 주제에 대한 전문성을 갖추고 있었다.": 5,
            "강사 만족도.강의 내용이 이해하기 쉽고 체계적으로 전달되었다.": 5,
            "강사 만족도.실습 진행과 안내가 원활했다.": 4,
            "강사 만족도.질문에 명확하고 충분하게 답변하였다.": 5,
            "학습효과.교육을 통해 새로운 지식과 기술을 습득했다.": 5,
            "학습효과.실제 업무에 적용할 수 있는 아이디어를 얻었다.": 4,
            "학습효과.교육 내용을 업무 또는 관련 활동에 활용할 수 있다고 생각한다.": 5,
            "학습효과.AI를 활용하는 데 대한 자신감이 향상되었다.": 5,
            "이번 교육에서 가장 도움이 되었던 내용과 향후 보완되었으면 하는 점을 자유롭게 작성해 주세요.":
                "실습 위주라 도움이 많이 됐고, 시간이 조금 더 보완되었으면 합니다",
        },
    }
    r = client.post("/webhook/forms?survey=support", headers=H, json=support_record)
    assert r.status_code == 200 and r.json()["total"] == 1, r.text
    # 훈련비 탭은 그대로 2건이어야 함(서로 섞이지 않음)
    s_train = client.get("/api/status?survey=training").json()
    assert s_train["rows"] == 2, s_train
    d = client.get("/api/dashboard?survey=support&course=전체").json()
    assert d["kpi"]["respondents"] == 1, d["kpi"]
    names = {i["name"] for i in d["items"]}
    assert names == {
        "참여목적 부합", "난이도", "이론/실습 구성", "교육 자료", "교육 시간",
        "강사 전문성", "수업 전달력", "실습 진행", "질문 응답",
        "지식 습득", "업무 아이디어", "실무 활용", "AI 활용 자신감",
    }, names
    assert _MEM["support"] and _MEM["support"]["rows"] == 1, _MEM["support"]
    kw = d["keywords"]
    assert kw["positive"] or kw["negative"], "지원비 주관식(보완 문구) 응답이 인식되지 않음"
    print(f"[8] support survey OK (독립 상태 확인, 13개 항목 매핑={len(names)}개, "
          f"주관식 인식={bool(kw['positive'] or kw['negative'])})")

    print("\n[OK] 전체 통과")


if __name__ == "__main__":
    main()
