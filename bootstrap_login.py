"""
bootstrap_login.py — 최초 1회 delegated 로그인(로컬에서 실행).

device-flow 로 로그인하면 MSAL 토큰 캐시가 Gist(token_cache.json)에 저장되어,
이후 Render 서버가 그 캐시로 silent 갱신만으로 무인 동작한다.

실행:
    venv/Scripts/python.exe bootstrap_login.py
화면에 뜨는 URL 로 접속해 코드를 입력하고 회사 계정으로 로그인하세요.
"""
import graph
import store


def main():
    print("[1/3] device-flow 로그인 시작...\n")
    graph.login_device_flow()

    print("\n[2/3] 토큰 캐시 Gist 저장 확인 중...")
    cached = store.load_token_cache()
    if not cached:
        print("  [경고] Gist 에 token_cache.json 이 저장되지 않았습니다. "
              "GITHUB_TOKEN 의 gist 권한을 확인하세요.")
        return
    print(f"  OK — token_cache.json 저장됨 (len={len(cached)})")

    print("\n[3/3] silent 토큰 재발급 테스트...")
    token = graph.get_token_silent()
    if token:
        print("  OK — 무인 갱신 가능. 이제 inspect_list.py 를 실행하세요.")
    else:
        print("  [경고] silent 재발급 실패. 다시 로그인해 보세요.")


if __name__ == "__main__":
    main()
