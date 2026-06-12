"""
inspect_list.py — SharePoint 리스트의 실제 컬럼(내부이름↔표시이름)과 샘플을 출력.

bootstrap_login.py 로 로그인한 뒤 실행:
    venv/Scripts/python.exe inspect_list.py
출력된 표시이름을 보고 graph.COLUMN_ALIAS 보정 여부를 결정한다.
"""
import json

import graph


def main():
    info = graph.inspect_columns()
    print(f"리스트: {info['list_name']}")
    print(f"GUID  : {info['list_id']}   ← config.py SHAREPOINT_LIST_ID 에 넣으면 가장 안정적\n")
    print("== 컬럼 (내부이름 → 표시이름) ==")
    for name, disp in info["columns"].items():
        print(f"  {name:35} → {disp}")
    print("\n== 샘플 응답 1건의 필드 키 ==")
    print(json.dumps(list(info["sample_fields"].keys()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
