"""
analyzer.py

업로드된 설문 Excel 을 읽어서 대시보드에 필요한 지표를 계산한다.
(훈련비과정 만족도 조사 전용 — 엘리스랩 폼 기준)

설계 메모:
- 12개 평가항목의 정확한 컬럼명(질문 전문)은 데이터마다 다를 수 있으므로,
  질문에 포함된 키워드로 "짧은 항목명 + 카테고리"를 매핑한다(ITEM_MAP).
  예) "...난이도와 구성이..." → 내용 구성(교육 구성),
      "강사의 전문성..."     → 강사 전문성(강사 역량).
- 매핑에 걸리지 않는 컬럼은 질문 전문을 줄여서 이름으로 쓰고 카테고리는 추정.
"""

import json
import re
from collections import Counter

import pandas as pd


# ---------------------------------------------------------------------------
# 평가항목 범위 식별 (질문 전문 일부)
# ---------------------------------------------------------------------------
RATING_START_KEYWORDS = ["교육 내용", "난이도"]   # 교육 내용의 난이도와 구성이 적절했다
RATING_END_KEYWORDS = ["실무", "적용"]            # 실무에 적용이 가능하다고 생각한다.

CATEGORY_ORDER = ["교육 구성", "강사 역량", "교육 효과"]

# (키워드 목록, 짧은 항목명, 카테고리) — 위에서부터 먼저 매칭(any-match)
ITEM_MAP = [
    (["난이도", "구성"], "내용 구성", "교육 구성"),
    (["자료", "교재"], "교육 자료", "교육 구성"),
    (["환경", "시설", "장비"], "교육 환경", "교육 구성"),
    (["시간", "일정"], "교육 시간", "교육 구성"),
    (["운영", "지원", "안내"], "운영·지원", "교육 구성"),
    (["전문"], "강사 전문성", "강사 역량"),
    (["전달", "설명"], "수업 전달력", "강사 역량"),
    (["질문", "답변"], "질문 응답", "강사 역량"),
    (["참여", "유도", "소통", "분위기"], "참여 유도", "강사 역량"),
    (["지식", "습득"], "지식 습득", "교육 효과"),
    (["목표", "달성", "기대"], "목표 달성", "교육 효과"),
    (["실무", "적용", "활용"], "실무 적용", "교육 효과"),
]

# 매핑 실패 시 카테고리 추정 규칙
FALLBACK_RULES = [
    ("강사 역량", ["강사"]),
    ("교육 효과", ["효과", "도움", "실무", "적용", "향상", "추천", "만족"]),
]
DEFAULT_CATEGORY = "교육 구성"

# ---- 주관식 키워드 분석 (규칙 기반, API 불필요) ----
# 무의미어 / 어미 / 접속어 / 도메인 필러: 토큰 자체를 제거
STOPWORDS = {
    # 무의미어
    "정말", "너무", "많이", "조금", "약간", "그냥", "매우", "아주", "더", "잘", "좀",
    "거", "것", "수", "등", "및", "또", "다시", "이런", "저런", "그런", "계속", "그래도",
    # 어미·서술어(토큰 형태)
    "했다", "됩니다", "있다", "없다", "같다", "좋다", "했습니다", "되었다", "해서",
    "하고", "하는", "인것", "것같", "것같다", "합니다", "입니다", "였다", "한다",
    # 접속어
    "그리고", "그러나", "하지만", "그래서", "또한", "그런데", "따라서",
    # 도메인 필러(모두가 공통으로 쓰는 단어)
    "교육", "강의", "수업", "강좌", "과정", "엘리스", "엘리스랩", "센터",
    "부분", "생각", "정도", "경우", "전반", "전반적",
}
# 조사: 토큰 끝에서 떼어냄(긴 것부터)
# 단음절 조사 중 명사 끝글자와 충돌이 잦은 것(도/로/나/만)은 제외해 과도한 절단 방지
JOSA = ["으로서", "으로써", "이라고", "에서는", "으로", "에서", "이나", "이랑", "에게",
        "한테", "까지", "부터", "처럼", "보다", "에는", "라고",
        "은", "는", "이", "가", "을", "를", "와", "과", "의", "에", "랑"]
# 어미: 토큰 끝에서 떼어내 어간만 남김
EOMI_SUFFIX = ["했습니다", "됐습니다", "되었다", "됩니다", "습니다", "했다", "됐다",
               "합니다", "입니다", "었다", "았다", "였다", "한다", "된다", "해요",
               "어요", "아요", "에요", "예요", "네요", "지만"]
SUFFIXES = sorted(set(JOSA + EOMI_SUFFIX), key=len, reverse=True)
# 무응답 처리
NO_RESPONSE = {"x", "X", "-", "", ".", "없음", "없다", "없습니다", "무", "na", "n/a"}

# 감성 단서(구간 분류용). 부정/개선을 우선 판정한다.
POS_CUES = ["좋았", "좋아", "도움", "만족", "유익", "유용", "최고", "감사", "추천",
            "훌륭", "알찬", "알차", "친절", "명확", "이해", "재미", "흥미", "쉽게",
            "깔끔", "체계"]
NEG_CUES = ["아쉽", "아쉬", "부족", "개선", "어려", "힘들", "짧", "빠르", "느리",
            "불편", "바라", "했으면", "좋겠", "필요", "보완", "추가", "늘려", "줄여",
            "많았으면", "적었", "복잡", "헷갈", "미흡", "문제", "불만", "지루", "과하"]

TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}")
CONTRAST_RE = re.compile(r"(하지만|그러나|그런데|반면|지만|으나|는데)")


# ---------------------------------------------------------------------------
# 로드 / 컬럼 헬퍼
# ---------------------------------------------------------------------------
def load_dataframe(path_or_buffer):
    df = pd.read_excel(path_or_buffer)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _norm(s):
    return str(s).replace(" ", "")


def find_col(df, *keywords):
    nkws = [_norm(k) for k in keywords]
    for col in df.columns:
        ncol = _norm(col)
        if all(k in ncol for k in nkws):
            return col
    return None


def get_course_col(df):
    return (
        find_col(df, "수강", "선택")
        or find_col(df, "교육을 선택")
        or find_col(df, "강좌")
    )


def get_rating_columns(df):
    cols = list(df.columns)
    start = find_col(df, *RATING_START_KEYWORDS)
    end = find_col(df, *RATING_END_KEYWORDS)
    if start in cols and end in cols:
        i, j = cols.index(start), cols.index(end)
        candidate = cols[min(i, j): max(i, j) + 1]
    else:
        candidate = cols
    rating = []
    for c in candidate:
        if pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.5:
            rating.append(c)
    return rating


def _fallback_category(col):
    for cat, kws in FALLBACK_RULES:
        if any(k in col for k in kws):
            return cat
    return DEFAULT_CATEGORY


def resolve_item(col, used):
    """질문 전문 -> (짧은 이름, 카테고리). used 로 이름 중복을 방지."""
    for kws, name, cat in ITEM_MAP:
        if any(k in col for k in kws):
            uniq, n = name, 2
            while uniq in used:
                uniq = f"{name} {n}"
                n += 1
            used.add(uniq)
            return uniq, cat
    name = _short(col, 14)
    while name in used:
        name += " "
    used.add(name)
    return name, _fallback_category(col)


def get_courses(df):
    course_col = get_course_col(df)
    if not course_col:
        return []
    vals = df[course_col].dropna().astype(str).str.strip()
    vals = vals[vals != ""]
    return sorted(vals.unique().tolist())


def get_subjective_responses(df):
    """주관식(도움/개선) 응답 텍스트 목록을 반환한다 (AI 분석 입력용)."""
    col = find_col(df, "도움", "개선") or find_col(df, "느낀")
    if not col:
        return []
    return [str(v).strip() for v in df[col].dropna().astype(str) if str(v).strip()]


# ---------------------------------------------------------------------------
# 안전한 평균 / 문자열 자르기
# ---------------------------------------------------------------------------
def _mean(series):
    s = pd.to_numeric(series, errors="coerce").dropna()
    return round(float(s.mean()), 2) if len(s) else 0.0


def _short(label, n=18):
    label = str(label).strip()
    return label if len(label) <= n else label[: n - 1] + "…"


# ---------------------------------------------------------------------------
# 주관식 분석
# ---------------------------------------------------------------------------
def _strip_suffix(tok):
    """조사·어미를 토큰 끝에서 떼어 어간을 남긴다(최대 2회)."""
    for _ in range(2):
        for s in SUFFIXES:
            if tok.endswith(s) and len(tok) - len(s) >= 2:
                tok = tok[: -len(s)]
                break
        else:
            break
    return tok


def _clean_tokens(text):
    """2글자 이상 의미 토큰 목록(불용어·무응답 제거, 조사/어미 정리)."""
    out = []
    for raw in TOKEN_RE.findall(text):
        t = raw.lower() if raw.isascii() else _strip_suffix(raw)
        if len(t) < 2 or t in STOPWORDS or t in NO_RESPONSE:
            continue
        out.append(t)
    return out


def _segments(text):
    """문장 종결/대조 연결어 기준으로 구간을 나눈다(긍·부정 혼재 분리)."""
    segs = []
    for part in re.split(r"[.!?…\n;]", text):
        for s in CONTRAST_RE.sub("|", part).split("|"):
            s = s.strip()
            if s:
                segs.append(s)
    return segs


def _extract_keywords(segments, top=18):
    """단어 + 복합어(bigram) 빈도. 2회 이상 등장한 복합어를 우선 채택."""
    uni, bi = Counter(), Counter()
    for seg in segments:
        toks = _clean_tokens(seg)
        uni.update(toks)
        for a, b in zip(toks, toks[1:]):
            if a != b:
                bi[f"{a} {b}"] += 1
    phrases = {p: c for p, c in bi.items() if c >= 2}
    result = Counter(phrases)
    for w, c in uni.items():
        # 채택된 복합어에 포함되고 빈도가 비슷한 단어는 중복 제거
        if any(w in p.split() and phrases[p] >= c * 0.6 for p in phrases):
            continue
        result[w] = c
    return [{"word": w, "count": c} for w, c in result.most_common(top)]


def analyze_keywords(responses):
    """주관식 응답을 긍정/개선 맥락으로 분류하고 키워드를 추출한다."""
    pos_segs, neg_segs = [], []
    for text in responses:
        t = str(text).strip()
        if not t or t in NO_RESPONSE:
            continue
        for seg in _segments(t):
            if any(c in seg for c in NEG_CUES):      # 개선/아쉬움 우선
                neg_segs.append(seg)
            elif any(c in seg for c in POS_CUES):    # 긍정
                pos_segs.append(seg)
            # 중립 구간은 키워드 클라우드에서 제외
    return {
        "positive": _extract_keywords(pos_segs),
        "negative": _extract_keywords(neg_segs),
    }


# 희망 훈련 과정: 객관식 옵션 화이트리스트(차트용). 그 외 값은 "기타 직접입력"으로 분리.
# 폼 옵션이 바뀌면 이 목록만 갱신하면 된다.
WISHED_OPTIONS = [
    "인공지능(AI) 실무 활용",
    "업무자동화(RPA 등)",
    "데이터 분석 & 시각화",
    "빅데이터 활용",
    "프로젝트 관리",
    "웹 개발 (Frontend/Backend)",
    "프로젝트 관리 (PM/Agile)",
    "클라우드 기반 개발 환경",
]


def wished_breakdown(series, top=10):
    """희망 과정 응답을 객관식 옵션(options)과 자유입력(other)으로 분리한다.
    - options: 화이트리스트에 해당 → 막대 차트용 (공백 차이 무시 매칭)
    - other:   그 외 자유입력 → 별도 목록 (의미없는 입력은 제외)"""
    opt_by_norm = {_norm(o): o for o in WISHED_OPTIONS}
    options, other = Counter(), Counter()
    for text in series.dropna().astype(str):
        for p in _explode_multi(text):
            p = p.strip()
            if not p or p in {"없음", "없다", "-"}:
                continue
            canon = opt_by_norm.get(_norm(p))
            if canon:
                options[canon] += 1
            elif len(p) >= 2 and re.search(r"[가-힣A-Za-z0-9]", p):  # 의미없는 입력 제외
                other[p] += 1
    return {
        "options": [{"course": k, "count": v} for k, v in options.most_common(top)],
        "other": [{"text": k, "count": v} for k, v in other.most_common()],
    }


def _explode_multi(text):
    """다중선택 값을 항목 리스트로 분해한다.
    두 포맷을 모두 지원:
      - 세미콜론/줄바꿈 구분 (Excel 가져오기 historical: "A;B;")
      - JSON 배열 문자열 (Power Automate Forms 다중선택: '["A","B"]')
    콤마로는 자르지 않는다("데이터 분석, 시각화" 같은 항목명 보존)."""
    t = (text or "").strip()
    if t.startswith("[") and t.endswith("]"):
        try:
            arr = json.loads(t)
            if isinstance(arr, list):
                return [str(x) for x in arr]
        except (ValueError, TypeError):
            pass
    return re.split(r"[;\n]", t)


def split_multi(series, top=10):
    counter = Counter()
    for text in series.dropna().astype(str):
        for p in _explode_multi(text):
            p = p.strip()
            if not p or p in {"없음", "없다", "-"}:
                continue
            counter[p] += 1
    return [{"course": k, "count": v} for k, v in counter.most_common(top)]


def newsletter_breakdown(series):
    yes = no = 0
    for v in series.dropna().astype(str):
        t = v.strip()
        if any(k in t for k in ["네", "예", "yes", "동의", "Y"]):
            yes += 1
        elif any(k in t for k in ["아니", "no", "비동의", "N"]):
            no += 1
    return {"네": yes, "아니오": no}


def course_ranking(df, rating_cols):
    course_col = get_course_col(df)
    if not course_col or not rating_cols:
        return []
    rows = []
    for course, sub in df.groupby(course_col):
        course = str(course).strip()
        if not course or course == "nan":
            continue
        vals = pd.to_numeric(sub[rating_cols].stack(), errors="coerce").dropna()
        score = round(float(vals.mean()), 2) if len(vals) else 0.0
        rows.append({"course": course, "score": score, "count": int(len(sub))})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# 메인 분석
# ---------------------------------------------------------------------------
def analyze(df, courses=None, filename=None):
    """courses: 선택된 강좌 목록. None/빈값/"전체" 포함 시 전체.
    여러 개면 그 강좌들 응답을 합쳐서 평균을 낸다."""
    rating_cols = get_rating_columns(df)
    course_col = get_course_col(df)
    selected = [str(c).strip() for c in (courses or [])
                if c and str(c).strip() and str(c).strip() != "전체"]

    # 컬럼 -> 메타(이름/카테고리) 1회 계산
    used = set()
    meta = {}
    for col in rating_cols:
        name, cat = resolve_item(col, used)
        meta[col] = {"name": name, "label": str(col).strip(), "category": cat}

    # 필터 적용 (선택된 강좌들의 합집합)
    if selected and course_col:
        sub = df[df[course_col].astype(str).str.strip().isin(selected)]
    else:
        sub = df

    # 항목별 점수
    items = [
        {
            "name": meta[c]["name"],
            "label": meta[c]["label"],
            "category": meta[c]["category"],
            "score": _mean(sub[c]),
        }
        for c in rating_cols
    ]

    # 카테고리별 평균
    cat_scores = {}
    for cat in CATEGORY_ORDER:
        cols = [c for c in rating_cols if meta[c]["category"] == cat]
        if cols:
            vals = pd.to_numeric(sub[cols].stack(), errors="coerce").dropna()
            cat_scores[cat] = round(float(vals.mean()), 2) if len(vals) else 0.0
        else:
            cat_scores[cat] = 0.0

    # 전체 평균
    if rating_cols:
        all_vals = pd.to_numeric(sub[rating_cols].stack(), errors="coerce").dropna()
        overall = round(float(all_vals.mean()), 2) if len(all_vals) else 0.0
    else:
        overall = 0.0

    # 주관식 / 다중선택 / 소식수신
    subj_col = find_col(df, "도움", "개선") or find_col(df, "느낀")
    wish_col = find_col(df, "추후", "훈련") or find_col(df, "진행했으면")
    news_col = find_col(df, "소식") or find_col(df, "받아보")

    subj_responses = (
        [str(v) for v in sub[subj_col].dropna().astype(str) if str(v).strip()]
        if subj_col else []
    )
    keywords = analyze_keywords(subj_responses)
    wished = wished_breakdown(sub[wish_col]) if wish_col else {"options": [], "other": []}
    newsletter = newsletter_breakdown(sub[news_col]) if news_col else {"네": 0, "아니오": 0}

    # 강좌별 항목 비교 (전체 기준, 카테고리 순 정렬)
    courses = get_courses(df)
    ordered_cols = sorted(
        rating_cols,
        key=lambda c: CATEGORY_ORDER.index(meta[c]["category"])
        if meta[c]["category"] in CATEGORY_ORDER else 99,
    )
    item_order = [meta[c]["name"] for c in ordered_cols]
    course_scores = {}
    if course_col:
        for cname in courses:
            csub = df[df[course_col].astype(str).str.strip() == cname]
            course_scores[cname] = {meta[c]["name"]: _mean(csub[c]) for c in ordered_cols}

    return {
        "filename": filename,
        "selected_courses": selected,
        "courses": courses,
        "kpi": {
            "overall": overall,
            "instructor": cat_scores.get("강사 역량", 0.0),
            "effect": cat_scores.get("교육 효과", 0.0),
            "respondents": int(len(sub)),
            "course_count": len(courses),
        },
        "categories": [{"name": cat, "score": cat_scores[cat]} for cat in CATEGORY_ORDER],
        "items": items,
        "course_ranking": course_ranking(df, rating_cols),
        "keywords": keywords,
        "newsletter": newsletter,
        "wished_courses": wished["options"],   # 막대 차트 = 객관식 옵션만
        "wished_other": wished["other"],       # 기타 직접입력 의견 목록
        "item_order": item_order,
        "course_scores": course_scores,
    }
