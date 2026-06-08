"""
ai_keywords.py

주관식 응답 전체를 Claude API(anthropic SDK)로 한 번에 분석한다.
- 단순 단어 빈도가 아니라 의미 단위 키워드/주제를 추출
- 긍정 / 개선·부정 카테고리로 분류 + 전체 요약
- 파일 업로드 시 1회만 호출하고 결과를 STATE 에 캐싱(app.py)

모델: config.CLAUDE_MODEL (기본 claude-sonnet-4-20250514)
키가 없거나 호출 실패 시 None / {"error": ...} 을 반환 → 프론트는 단어 빈도로 폴백.

설계 메모:
- 이 모델은 structured outputs(output_config.format)를 지원하지 않으므로
  프롬프트로 JSON 형식을 강제하고 견고하게 파싱한다(코드펜스 제거 + 중괄호 추출).
- 시스템 프롬프트는 업로드마다 동일하므로 prompt caching(cache_control)을 적용.
"""

import json
import os
import re

# config.py 는 로컬 전용(gitignore). 배포 환경에는 없을 수 있으므로 안전하게 import.
try:
    import config
except ModuleNotFoundError:
    config = None


def _cfg(name, default=""):
    """환경변수 우선, 없으면 config.py, 그것도 없으면 default."""
    val = os.environ.get(name)
    if val:
        return val
    if config is not None:
        return getattr(config, name, default)
    return default

SYSTEM_PROMPT = (
    "당신은 교육 만족도 조사 분석 전문가입니다. 수강생들의 주관식 응답을 분석해 "
    "의미 있는 키워드와 주제를 추출합니다.\n"
    "- 단순 단어 빈도가 아니라 '의미 단위'로 묶으세요. "
    "예) 'AI 활용', '실무 적용', '난이도 조절', '시간 부족', '실습 중심', '강사 친절'.\n"
    "- positive: 수강생이 긍정적으로 자주 언급한 키워드.\n"
    "- negative: 개선 요청·부정적으로 자주 언급한 키워드.\n"
    "- count: 해당 키워드가 언급된 정도(많을수록 큰 정수로 추정).\n"
    "- summary: 전체 응답 경향을 2~3문장으로 요약.\n"
    "반드시 아래 JSON 형식 '그 자체로만' 응답하세요. 마크다운 코드펜스(```)나 "
    "설명 문장을 절대 덧붙이지 마세요.\n"
    "{\n"
    '  "positive": [{"keyword": "키워드", "count": 정수}, ... 최대 10개],\n'
    '  "negative": [{"keyword": "키워드", "count": 정수}, ... 최대 10개],\n'
    '  "summary": "2~3문장 요약"\n'
    "}"
)


def _parse_json(text):
    """코드펜스/잡음을 제거하고 JSON 객체를 추출한다."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)  # 첫 { ~ 마지막 }
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _norm(items):
    out = []
    for it in (items or [])[:10]:
        if isinstance(it, dict) and it.get("keyword"):
            try:
                cnt = int(it.get("count", 1) or 1)
            except (TypeError, ValueError):
                cnt = 1
            out.append({"keyword": str(it["keyword"]).strip(), "count": cnt})
        elif isinstance(it, str) and it.strip():
            out.append({"keyword": it.strip(), "count": 1})
    return out


def analyze_subjective(responses):
    key = (_cfg("ANTHROPIC_API_KEY", "") or "").strip()
    responses = [str(r).strip() for r in (responses or []) if r and str(r).strip()]
    if not key or not responses:
        return None  # 미설정 → 단어 빈도 폴백

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic 패키지가 설치되어 있지 않습니다 (pip install anthropic)."}

    model = _cfg("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    joined = "\n".join(f"- {r}" for r in responses)
    user_content = (
        f"다음은 교육 만족도 조사의 주관식 응답 {len(responses)}건입니다. "
        f"분석해서 지정된 JSON으로 반환해 주세요.\n\n{joined}"
    )

    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # 업로드 간 시스템 프롬프트 캐싱
            }],
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:  # noqa: BLE001 — 네트워크/인증/모델 오류를 폴백으로 처리
        return {"error": f"Claude API 호출 실패: {e}"}

    text = "".join(
        getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
    )
    data = _parse_json(text)
    if not isinstance(data, dict):
        return {"error": "Claude 응답 JSON 파싱 실패"}

    return {
        "positive": _norm(data.get("positive")),
        "negative": _norm(data.get("negative")),
        "summary": str(data.get("summary", "")).strip(),
        "respondents": len(responses),
    }
