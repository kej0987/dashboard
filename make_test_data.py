"""테스트용 합성 설문 Excel 생성 (검증 전용)."""
import random
import pandas as pd

random.seed(42)

COURSE_COL = "수강하신 교육을 선택해 주세요"
ITEMS = [
    "교육 내용의 난이도와 구성이 적절했다",        # 내용 구성
    "제공된 교육 자료와 교재가 충실했다",           # 교육 자료
    "교육 환경과 시설이 쾌적했다",                  # 교육 환경
    "교육 시간과 일정이 적절했다",                  # 교육 시간
    "교육 운영과 지원이 원활했다",                  # 운영·지원
    "강사의 전문성이 높았다",                       # 강사 전문성
    "강사의 설명 전달력이 우수했다",                # 수업 전달력
    "강사가 질문에 성실히 답변했다",                # 질문 응답
    "강사가 학습자의 참여를 적극 유도했다",         # 참여 유도
    "교육을 통해 새로운 지식을 습득했다",           # 지식 습득
    "교육 목표를 달성했다",                         # 목표 달성
    "실무에 적용이 가능하다고 생각한다.",           # 실무 적용
]
SUBJ = "특히 도움이 된 부분 혹은 개선이 필요하다고 느낀 부분이 있나요?"
WISH = "추후 진행했으면 하는 재직자 훈련 과정이 있다면?"
NEWS = "앞으로 엘리스랩에서 진행하는 교육이나 행사 소식을 받아보시겠습니까?"

courses = ["파이썬 데이터분석", "AI 활용 실무", "웹 개발 입문", "클라우드 기초"]
wish_pool = ["딥러닝 심화", "데이터 시각화", "SQL 실무", "AWS 자격증",
             "프로젝트 관리", "디자인 씽킹"]
subj_pool = [
    "실습 위주의 강의가 정말 도움이 되었습니다. 강사님이 친절했어요.",
    "이론이 조금 어려웠지만 실무 예제가 좋았습니다. 시간이 부족했어요.",
    "강사님의 전달력이 훌륭했고 질문에 잘 답변해 주셨습니다.",
    "교재가 충실했고 실무에 바로 적용할 수 있을 것 같습니다.",
    "난이도 조절이 필요해 보입니다. 그래도 전반적으로 만족합니다.",
    "프로젝트 실습 시간이 더 있었으면 좋겠습니다. 내용은 알찼어요.",
]

rows = []
for _ in range(120):
    course = random.choice(courses)
    base = random.uniform(3.5, 4.8)
    row = {COURSE_COL: course}
    for it in ITEMS:
        row[it] = max(1, min(5, round(base + random.uniform(-0.8, 0.8))))
    row[SUBJ] = random.choice(subj_pool)
    row[WISH] = ";".join(random.sample(wish_pool, random.randint(1, 3)))
    row[NEWS] = random.choice(["네", "네", "네", "아니오"])
    rows.append(row)

df = pd.DataFrame(rows)
df.to_excel("test_survey.xlsx", index=False, sheet_name="설문결과")
print(f"생성 완료: test_survey.xlsx ({len(df)}행, {len(df.columns)}열)")
