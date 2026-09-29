"""에이전트 동작 확인용 데모 서비스. 로그인 → 마이페이지 → 회원탈퇴 → 완료.

실제 사이트처럼 로그인해야 마이페이지가 보이고, 탈퇴는 안내 확인 체크 후에만 된다.
IDLY_DEMO=1일 때 보고서에 '데모 서비스' 계정이 함께 나와 화면에서 흐름을 끝까지 해볼 수 있다.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(prefix="/demo")

_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>데모 서비스</title>
<style>body{{font-family:system-ui,sans-serif;max-width:520px;margin:60px auto;line-height:1.6}}
input,button{{font:inherit;padding:8px 12px;margin:4px 0}}a{{color:#1a4}}</style></head>
<body><h1>데모 서비스</h1>{body}</body></html>"""


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(body=body))


def _logged_in(request: Request) -> bool:
    return request.cookies.get("demo_user") is not None


@router.get("/mypage")
def mypage(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/demo/login", status_code=303)
    return _page(f"<h2>마이페이지</h2><p>{request.cookies['demo_user']}님, 안녕하세요.</p>"
                 "<ul><li><a href='/demo/profile'>내 정보</a></li><li><a href='/demo/withdraw'>회원탈퇴</a></li></ul>")


@router.get("/login")
def login_form():
    return _page("<h2>로그인</h2><form method='post' action='/demo/login'>"
                 "<div><input name='user' placeholder='아이디'></div>"
                 "<div><input name='password' type='password' placeholder='비밀번호'></div>"
                 "<button type='submit'>로그인</button></form>")


@router.post("/login")
def login(user: str = Form(""), password: str = Form("")):
    if not user or not password:
        return _page("<p>아이디와 비밀번호를 입력해주세요.</p><a href='/demo/login'>다시 로그인</a>")
    response = RedirectResponse("/demo/mypage", status_code=303)
    response.set_cookie("demo_user", user)
    return response


@router.get("/withdraw")
def withdraw_form(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/demo/login", status_code=303)
    return _page("<h2>회원탈퇴</h2><p>탈퇴하면 모든 데이터가 삭제되며 되돌릴 수 없습니다.</p>"
                 "<form method='post' action='/demo/withdraw'>"
                 "<label><input type='checkbox' id='agree' name='agree' value='1'> 안내 사항을 확인했습니다</label>"
                 "<div><button type='submit'>탈퇴하기</button></div></form>")


@router.post("/withdraw")
def withdraw(request: Request, agree: str = Form("")):
    if not _logged_in(request):
        return RedirectResponse("/demo/login", status_code=303)
    if agree != "1":
        return _page("<p>안내 사항 확인에 체크해주세요.</p><a href='/demo/withdraw'>돌아가기</a>")
    response = _page("<h2>탈퇴가 완료되었습니다</h2><p>그동안 이용해주셔서 감사합니다.</p>")
    response.delete_cookie("demo_user")
    return response
