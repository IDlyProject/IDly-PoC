"""서비스별 계정 조치 흐름.

AI가 아무 사이트나 알아서 처리하게 하지 않는다. 서비스·조치마다 단계를 먼저 정의하고,
실제 계정으로 선택자를 확인한 흐름만 verified=True로 둔다. 검증된 흐름이 없는 서비스는
'직접 처리 안내'로 넘긴다.

단계 종류
- goto:    url로 이동
- click:   text(보이는 글자) 또는 selector(CSS)로 찾아 클릭. 못 찾으면 AI 스크린샷 보조 → 그래도 없으면 사용자에게 넘김
- fill:    selector 입력칸에 value 입력
- user:    사용자 개입 (로그인·본인인증). until_text / until_url 이 보이면 자동으로 다음 단계로
- confirm: 되돌릴 수 없는 버튼 직전. 사용자가 확정해야 다음 단계로
- expect:  text가 보이면 완료로 본다
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Step:
    kind: str
    label: str
    url: Optional[str] = None
    text: Optional[str] = None
    selector: Optional[str] = None
    value: Optional[str] = None
    until_text: Optional[str] = None
    until_url: Optional[str] = None


@dataclass
class Flow:
    domain: str
    action: str  # 탈퇴 | 구독 해지 | 권한 해제
    steps: List[Step]
    verified: bool = False
    note: str = ""


# 서버 자기 주소 (데모 서비스가 여기서 돈다). 클라우드 브라우저도 서버에서 돌므로 127.0.0.1로 충분하다
SELF_URL = os.getenv("IDLY_SELF_URL", "http://127.0.0.1:47821")
DEMO_DOMAIN = "idly-demo.test"

FLOWS: List[Flow] = [
    # 실행기 검증용 데모 서비스 (backend/actions/demo_site.py)
    Flow(
        domain=DEMO_DOMAIN,
        action="탈퇴",
        verified=True,
        note="IDly 에이전트 동작 확인용 데모",
        steps=[
            Step("goto", "데모 서비스 마이페이지 열기", url=f"{SELF_URL}/demo/mypage"),
            Step("user", "데모 서비스에 로그인해주세요 (아이디·비밀번호 아무거나)", until_text="마이페이지"),
            Step("click", "회원탈퇴 메뉴 열기", text="회원탈퇴"),
            Step("click", "탈퇴 안내 확인 체크", selector="#agree"),
            Step("confirm", "탈퇴하기를 누르면 데모 계정이 삭제돼요"),
            Step("click", "탈퇴하기 누르기", text="탈퇴하기"),
            Step("expect", "탈퇴 완료 확인", text="탈퇴가 완료되었습니다"),
        ],
    ),
    # 실제 서비스 흐름은 실제 계정으로 선택자를 확인한 뒤 verified=True로 추가한다.
]

_BY_KEY: Dict[Tuple[str, str], Flow] = {(f.domain, f.action): f for f in FLOWS}


def find_flow(domain: str, action: str) -> Optional[Flow]:
    flow = _BY_KEY.get((domain, action))
    return flow if flow and flow.verified else None


def supported_actions(domain: str) -> List[str]:
    return [f.action for f in FLOWS if f.domain == domain and f.verified]
