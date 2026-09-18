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


def _client(anthropic_module, key):
    """ANTHROPIC_BASE_URL 설정 시 그쪽(예: 엘리스클라우드 ML API 게이트웨이)으로 붙는다.
    그 게이트웨이는 Authorization: Bearer 방식이라 auth_token 을 쓴다.
    비어 있으면 기존처럼 api.anthropic.com 에 api_key 로 붙는다(순정 Anthropic 키용)."""
    base_url = (_cfg("ANTHROPIC_BASE_URL", "") or "").strip()
    if base_url:
        return anthropic_module.Anthropic(auth_token=key, base_url=base_url)
    return anthropic_module.Anthropic(api_key=key)

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
        client = _client(anthropic, key)
        resp = client.messages.create(
            model=model,
            # 응답이 많으면 모델이 extended thinking 을 자동으로 써서 추론 토큰을 먼저 소모한다
            # (게이트웨이 모델 기준 확인: 응답 120건 프롬프트에서 thinking_tokens ~2700).
            # max_tokens 가 작으면 사고만 하다 끝나(stop_reason=max_tokens) 본문이 비어버리므로 넉넉히 잡는다.
            max_tokens=4096,
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


OVERVIEW_INSTRUCTIONS = (
    "다음은 교육 만족도 조사 결과 통계와 주관식 키워드입니다(JSON). "
    "담당자가 다음 기수 운영에 바로 실행할 수 있는 분석을 아래 형식으로만, 줄바꿈으로 구분해서 "
    "작성하세요. 이모지나 마크다운 기호는 쓰지 마세요.\n\n"
    "잘하고 있는 것: (유지해야 할 부분. 점수가 가장 높은 항목/카테고리나 positive_keywords 를 "
    "구체적으로 인용)\n"
    "문제가 되는 것: (가장 시급한 문제 1가지. 점수가 낮은 항목이나 negative_keywords 를 "
    "구체적으로 인용하고, 왜 문제인지 한 마디 덧붙임)\n"
    "다음에 할 일: (위 문제를 해결하기 위한 구체적 액션 1~2가지. '검토가 필요합니다' 같은 "
    "말로 끝내지 말고 실제로 뭘 바꾸라는 건지 제안)\n\n"
    "절대 규칙:\n"
    "- '전반적으로 만족도가 높다', '균형 잡힌 평가를 받았다', '전반적으로 우수하다' 같은 "
    "누가 봐도 당연하고 두루뭉술한 문장은 절대 쓰지 마세요.\n"
    "- 모든 문장에 데이터에 실제로 있는 항목명·강좌명·키워드를 최소 1개 이상 반드시 인용하세요.\n"
    "- 각 줄은 1문장으로 간결하게, 존댓말로 작성하세요. 위 3줄 형식 그대로(라벨 뒤에 콜론), "
    "제목이나 다른 설명을 덧붙이지 마세요."
)


def analyze_overview(stats):
    """KPI/카테고리/항목/강좌순위/주관식 키워드를 바탕으로 실행 가능한 종합 분석을 생성한다.
    키가 없거나 실패하면 None 을 반환 → analyzer.overview_summary 규칙기반 문장으로 폴백."""
    key = (_cfg("ANTHROPIC_API_KEY", "") or "").strip()
    if not key:
        return None

    try:
        import anthropic
    except ImportError:
        return None  # 키워드 분석 쪽에서 이미 안내하므로 여기선 조용히 폴백

    model = _cfg("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    prompt = OVERVIEW_INSTRUCTIONS + "\n\n" + json.dumps(stats, ensure_ascii=False)
    try:
        client = _client(anthropic, key)
        resp = client.messages.create(
            model=model, max_tokens=1500,  # extended thinking 대비 여유(analyze_subjective 참고)
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:  # noqa: BLE001 — 실패 시 조용히 규칙기반 폴백
        return None

    text = "".join(
        getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
    ).strip()
    return {"summary": text} if text else None
