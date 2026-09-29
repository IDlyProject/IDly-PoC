"""IMAP으로 붙일 수 있는 메일 서비스 목록.

auth
- password: IMAP 비밀번호 로그인. 대부분 2단계 인증 + 앱 비밀번호가 필요하다.
- oauth_microsoft: Microsoft가 비밀번호 IMAP을 막아 OAuth로만 된다. IDly는 OAuth를 쓰지 않으므로 연동 불가로 표시된다.

steps: 사용자가 연동 전에 해야 하는 일. url이 있으면 그 설정 페이지로 바로 보낸다.
password_label: 비밀번호 입력칸 이름 (서비스마다 앱 비밀번호 필요 여부가 다르다).
login_hint: 로그인 실패 시 보여줄 안내.
"""

from typing import Dict, List, Optional

PROVIDERS: List[dict] = [
    {
        "id": "gmail",
        "name": "Gmail",
        "domains": ["gmail.com", "googlemail.com"],
        "host": "imap.gmail.com",
        "auth": ["password"],
        "steps": [
            {"text": "Google 계정에서 2단계 인증 켜기", "url": "https://myaccount.google.com/security"},
            {"text": "앱 비밀번호 16자리 만들기", "url": "https://myaccount.google.com/apppasswords"},
        ],
        "password_label": "앱 비밀번호 (16자리)",
        "login_hint": "Google 계정 비밀번호가 아니라 앱 비밀번호를 입력했는지 확인해주세요.",
    },
    {
        "id": "naver",
        "name": "네이버 메일",
        "domains": ["naver.com"],
        "host": "imap.naver.com",
        "auth": ["password"],
        "steps": [
            {"text": "네이버 메일 환경설정 > POP3/IMAP 설정에서 IMAP 사용함으로 바꾸기", "url": "https://mail.naver.com"},
            {"text": "2단계 인증을 쓰고 있다면 애플리케이션 비밀번호 만들기", "url": "https://nid.naver.com/user2/help/myInfoV2?m=viewSecurity"},
        ],
        "password_label": "네이버 비밀번호 (2단계 인증을 쓰면 애플리케이션 비밀번호)",
        "login_hint": "IMAP 사용 설정이 켜져 있는지, 2단계 인증을 쓴다면 애플리케이션 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "daum",
        "name": "다음 메일",
        "domains": ["daum.net", "hanmail.net"],
        "host": "imap.daum.net",
        "auth": ["password"],
        "steps": [
            {"text": "다음 메일 환경설정 > IMAP/POP3에서 IMAP 사용하기", "url": "https://mail.daum.net"},
            {"text": "카카오 계정 2단계 인증을 쓰고 있다면 앱 비밀번호 만들기", "url": "https://accounts.kakao.com"},
        ],
        "password_label": "비밀번호 (2단계 인증을 쓰면 앱 비밀번호)",
        "login_hint": "IMAP 사용 설정이 켜져 있는지, 2단계 인증을 쓴다면 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "kakao",
        "name": "카카오 메일",
        "domains": ["kakao.com"],
        "host": "imap.kakao.com",
        "auth": ["password"],
        "steps": [
            {"text": "카카오 메일 환경설정 > IMAP/POP3에서 IMAP 사용하기", "url": "https://mail.kakao.com"},
            {"text": "카카오 계정 보안 설정에서 앱 비밀번호 만들기", "url": "https://accounts.kakao.com"},
        ],
        "password_label": "앱 비밀번호",
        "login_hint": "IMAP 사용 설정이 켜져 있는지, 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "nate",
        "name": "네이트 메일",
        "domains": ["nate.com"],
        "host": "imap.nate.com",
        "auth": ["password"],
        "steps": [{"text": "네이트 메일 환경설정 > POP3/IMAP 설정에서 IMAP 사용하기", "url": "https://www.nate.com"}],
        "password_label": "네이트 비밀번호",
        "login_hint": "IMAP 사용 설정이 켜져 있는지 확인해주세요.",
    },
    {
        "id": "outlook",
        "name": "Outlook / Hotmail",
        "domains": ["outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.kr", "hotmail.co.kr"],
        "host": "outlook.office365.com",
        "auth": ["oauth_microsoft"],
        "steps": [],
        "password_label": None,
        "login_hint": "Microsoft 로그인을 다시 시도해주세요.",
    },
    {
        "id": "icloud",
        "name": "iCloud 메일",
        "domains": ["icloud.com", "me.com", "mac.com"],
        "host": "imap.mail.me.com",
        "auth": ["password"],
        "steps": [{"text": "Apple 계정 > 로그인 및 보안 > 앱 암호 만들기", "url": "https://account.apple.com"}],
        "password_label": "앱 암호",
        "login_hint": "Apple 계정 암호가 아니라 앱 암호를 넣었는지 확인해주세요.",
    },
    {
        "id": "yahoo",
        "name": "Yahoo 메일",
        "domains": ["yahoo.com", "ymail.com", "rocketmail.com"],
        "host": "imap.mail.yahoo.com",
        "auth": ["password"],
        "steps": [{"text": "계정 보안에서 앱 비밀번호 만들기", "url": "https://login.yahoo.com/account/security"}],
        "password_label": "앱 비밀번호",
        "login_hint": "계정 비밀번호가 아니라 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "aol",
        "name": "AOL 메일",
        "domains": ["aol.com"],
        "host": "imap.aol.com",
        "auth": ["password"],
        "steps": [{"text": "계정 보안에서 앱 비밀번호 만들기", "url": "https://login.aol.com/account/security"}],
        "password_label": "앱 비밀번호",
        "login_hint": "계정 비밀번호가 아니라 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "zoho",
        "name": "Zoho 메일",
        "domains": ["zoho.com", "zohomail.com"],
        "host": "imap.zoho.com",
        "auth": ["password"],
        "steps": [
            {"text": "Zoho 메일 설정 > 메일 계정에서 IMAP 접근 켜기", "url": "https://mail.zoho.com"},
            {"text": "2단계 인증을 쓰고 있다면 앱 비밀번호 만들기", "url": "https://accounts.zoho.com/home#security/app_password"},
        ],
        "password_label": "비밀번호 (2단계 인증을 쓰면 앱 비밀번호)",
        "login_hint": "IMAP 접근이 켜져 있는지, 2단계 인증을 쓴다면 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "gmx",
        "name": "GMX",
        "domains": ["gmx.com"],
        "host": "imap.gmx.com",
        "auth": ["password"],
        "steps": [{"text": "GMX 설정 > POP3 & IMAP에서 외부 접근 켜기", "url": "https://www.gmx.com"}],
        "password_label": "GMX 비밀번호",
        "login_hint": "POP3 & IMAP 외부 접근이 켜져 있는지 확인해주세요.",
    },
    {
        "id": "yandex",
        "name": "Yandex 메일",
        "domains": ["yandex.com", "yandex.ru"],
        "host": "imap.yandex.com",
        "auth": ["password"],
        "steps": [
            {"text": "메일 설정 > 메일 프로그램에서 IMAP 켜기", "url": "https://mail.yandex.com"},
            {"text": "앱 비밀번호 만들기", "url": "https://id.yandex.com/security/app-passwords"},
        ],
        "password_label": "앱 비밀번호",
        "login_hint": "IMAP이 켜져 있는지, 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "fastmail",
        "name": "Fastmail",
        "domains": ["fastmail.com", "fastmail.fm"],
        "host": "imap.fastmail.com",
        "auth": ["password"],
        "steps": [{"text": "IMAP 권한으로 앱 비밀번호 만들기", "url": "https://app.fastmail.com/settings/security/apps"}],
        "password_label": "앱 비밀번호",
        "login_hint": "IMAP 권한이 있는 앱 비밀번호를 넣었는지 확인해주세요.",
    },
    {
        "id": "custom",
        "name": "기타 (IMAP 서버 직접 입력)",
        "domains": [],
        "host": None,
        "auth": ["password"],
        "steps": [],
        "password_label": "메일 비밀번호",
        "login_hint": "IMAP 서버 주소·포트와 비밀번호를 확인해주세요. 회사·학교 메일은 관리자가 IMAP을 막아 두었을 수 있어요.",
    },
]

_BY_ID: Dict[str, dict] = {p["id"]: p for p in PROVIDERS}


def get_provider(provider_id: str) -> Optional[dict]:
    return _BY_ID.get(provider_id)


def detect_provider(email: str) -> dict:
    domain = email.rsplit("@", 1)[-1].lower()
    for p in PROVIDERS:
        if domain in p["domains"]:
            return p
    return _BY_ID["custom"]
