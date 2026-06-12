"""
로컬 end-to-end 테스트 (실제 Gist 네트워크 호출 없음).

store.load_payload / save_payload 를 메모리 스텁으로 교체해
/webhook/forms upsert → /api/status version 증가 → /api/dashboard 반영을 검증한다.

실행: venv/Scripts/python.exe test_webhook_flow.py
"""
import os

os.environ["WEBHOOK_SECRET"] = "local-test-secret"

import store

# --- Gist 를 메모리로 대체 (네트워크/실데이터 보호) ---
_MEM = {"payload": None}
store.load_payload = lambda: _MEM["payload"]
def _save(records, filename, updated_at):
    _MEM["payload"] = {"filename": filename, "updated_at": updated_at,
                       "rows": len(records), "records": records}
    return True
store.save_payload = _save
# 토큰 캐시 읽기/쓰기도 네트워크 차단
store.load_token_cache = lambda: None
store.save_token_cache = lambda s: True

# Graph 비활성(부트스트랩 전 상태 모사) → /api/* 의 자동 갱신은 캐시로 폴백
import graph
graph.get_token_silent = lambda: None

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

    # 6) 강좌 필터
    d2 = client.get("/api/dashboard?course=데이터 분석").json()
    assert d2["kpi"]["respondents"] == 1, d2["kpi"]
    print(f"[6] course filter OK (데이터 분석 respondents={d2['kpi']['respondents']})")

    # 7) 영속 저장 확인(스텁 메모리)
    assert _MEM["payload"] and _MEM["payload"]["rows"] == 2, _MEM["payload"]
    rids = {r[appmod.RID_KEY] for r in _MEM["payload"]["records"]}
    assert rids == {"r1", "r2"}, rids
    print(f"[7] persist OK (저장된 응답ID={rids})")

    print("\n[OK] 전체 통과")


if __name__ == "__main__":
    main()
