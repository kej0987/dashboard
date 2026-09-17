"""테스트용 합성 지원비과정 설문 Excel 생성 (검증 전용).
컬럼명은 실제 SharePoint 표시이름 그대로 사용한다(Forms 섹션이 "카테고리." 접두사와
끝에 "."을 붙인다 — inspect_list.py support 로 확인한 실제 형태)."""
import random
import pandas as pd

random.seed(42)

COURSE_COL = "수강하신 교육을 선택해 주세요"
ITEMS = [
    " 교육 만족도.교육 내용이 참여 목적과 잘 부합했다.",
    " 교육 만족도.교육 난이도가 적절했다.",
    " 교육 만족도.이론/실습 구성이 적절했다.",
    " 교육 만족도.실습 및 교육 자료가 학습에 도움이 되었다.",
    " 교육 만족도.교육 시간이 내용을 학습하기에 적절했다.",
    "강사 만족도.교육 주제에 대한 전문성을 갖추고 있었다.",
    "강사 만족도.강의 내용이 이해하기 쉽고 체계적으로 전달되었다.",
    "강사 만족도.실습 진행과 안내가 원활했다.",
    "강사 만족도.질문에 명확하고 충분하게 답변하였다.",
    "학습효과.교육을 통해 새로운 지식과 기술을 습득했다.",
    "학습효과.실제 업무에 적용할 수 있는 아이디어를 얻었다.",
    "학습효과.교육 내용을 업무 또는 관련 활동에 활용할 수 있다고 생각한다.",
    "학습효과.AI를 활용하는 데 대한 자신감이 향상되었다.",
]
SUBJ = "이번 교육에서 가장 도움이 되었던 내용과 향후 보완되었으면 하는 점을 자유롭게 작성해 주세요."
WISH = "추후 진행했으면 하는 과정이 있다면? (복수 선택 가능)"
NEWS = "앞으로 엘리스랩에서 진행하는 교육이나 행사 소식을 받아보시겠습니까?"

courses = ["AI 활용 실무", "업무자동화(RPA)", "데이터 분석 기초", "프롬프트 엔지니어링"]
wish_pool = ["AI 실무 활용", "업무자동화(RPA)", "데이터 분석 & 시각화", "프로젝트 관리"]
subj_pool = [
    "실습 위주라 도움이 많이 됐고, 시간이 조금 더 보완되었으면 합니다.",
    "AI 활용 사례가 풍부해서 좋았습니다. 다만 난이도가 있었어요.",
    "강사님 설명이 명확했습니다. 실습 자료가 더 있으면 좋겠어요.",
    "실무에 바로 쓸 수 있는 내용이라 만족스러웠습니다.",
]

rows = []
for _ in range(43):
    course = random.choice(courses)
    base = random.uniform(3.8, 4.9)
    row = {COURSE_COL: course}
    for it in ITEMS:
        row[it] = max(1, min(5, round(base + random.uniform(-0.7, 0.7))))
    row[SUBJ] = random.choice(subj_pool)
    row[WISH] = ";".join(random.sample(wish_pool, random.randint(1, 2)))
    row[NEWS] = random.choice(["네", "네", "네", "아니오"])
    rows.append(row)

df = pd.DataFrame(rows)
df.to_excel("test_survey_support.xlsx", index=False, sheet_name="설문결과")
print(f"생성 완료: test_survey_support.xlsx ({len(df)}행, {len(df.columns)}열)")
