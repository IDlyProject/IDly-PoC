"""IDly 웹 백엔드. IMAP으로 메일을 받고 계정을 찾는다.

- 사용자는 IDly 계정(이메일+비밀번호)으로 가입·로그인하고, 메일함은 그 계정에 속한다.
- 메일 앱 비밀번호·토큰은 암호화해 저장하므로 다시 탐색할 때 다시 입력하지 않는다.
- 탐색 결과는 메일함별로 저장한다. 메일 원문은 저장하지 않는다.
"""

import imaplib
import os
import re
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import db  # noqa: E402
from analysis import demo_account  # noqa: E402
from actions import demo_site  # noqa: E402
from actions.flows import find_flow, supported_actions  # noqa: E402
from actions import extension_runs  # noqa: E402
from actions.extension_runs import ExtensionRun  # noqa: E402
from actions.runner import ActionRun, get_run, list_runs, start_run  # noqa: E402
from imap_sync import MAX_PER_FOLDER, Credential, SyncJob, connect, get_job, start_sync  # noqa: E402
from providers import PROVIDERS, detect_provider, get_provider  # noqa: E402

# 이 호스트 이름으로 온 요청만 받는다 (DNS 리바인딩 방지). 쉼표로 여러 개, "*.example.com" 와일드카드 가능.
# Render·Vercel에 배포하면 플랫폼이 넣어 주는 배포 주소도 자동으로 허용한다.
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host.strip()]
ALLOWED_HOSTS += [
    os.environ[name]
    for name in ("RENDER_EXTERNAL_HOSTNAME", "VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL")
    if os.getenv(name)
]
SESSION_COOKIE = "idly_session"

app = FastAPI(title="IDly web backend")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
# 에이전트 확인용 데모 서비스 (클라우드 브라우저가 여기서 로그인·탈퇴를 해 본다)
app.include_router(demo_site.router)

# 진행 중·최근 탐색 작업 (user_id, 메일) -> job id. 결과 자체는 DB에 저장된다
_running: Dict[Tuple[int, str], str] = {}


# --- 세션 -------------------------------------------------------------------------

def _user(request: Request) -> Optional[dict]:
    return db.session_user(request.cookies.get(SESSION_COOKIE, ""))


def _require_user(request: Request) -> dict:
    user = _user(request)
    if user is None:
        raise HTTPException(401, "로그인이 필요해요.")
    return user


def _start_session(response: Response, user_id: int) -> None:
    response.set_cookie(SESSION_COOKIE, db.create_session(user_id), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 30)


def _me(user: Optional[dict]) -> dict:
    if user is None:
        return {"user": None, "mailboxes": []}
    return {
        "user": {"email": user["email"]},
        "mailboxes": [
            {**m, "job_id": _running.get((user["id"], m["email"]))}
            for m in db.list_mailboxes(user["id"])
        ],
    }


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return _me(_user(request))


# --- IDly 계정 ----------------------------------------------------------------------

class AuthBody(BaseModel):
    email: str
    password: str


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@app.post("/api/auth/signup")
def signup(body: AuthBody, response: Response):
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(400, "이메일 형식을 확인해주세요.")
    if len(body.password) < 8:
        raise HTTPException(400, "비밀번호는 8자 이상이어야 해요.")
    user_id = db.create_user(body.email, body.password)
    if user_id is None:
        raise HTTPException(409, "이미 가입한 이메일이에요. 로그인해주세요.")
    _start_session(response, user_id)
    return _me(db.get_user(user_id))


@app.post("/api/auth/login")
def login(body: AuthBody, response: Response):
    user_id = db.verify_user(body.email, body.password)
    if user_id is None:
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않아요.")
    _start_session(response, user_id)
    return _me(db.get_user(user_id))


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    db.delete_session(request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE)
    return _me(None)


# --- 메일함 -------------------------------------------------------------------------

@app.get("/api/providers")
def providers():
    # OAuth는 쓰지 않는다. 앱 비밀번호 IMAP만 (Outlook처럼 막힌 곳은 auth가 비어 '연동 불가'로 보인다)
    return [{**p, "auth": [a for a in p["auth"] if a == "password"]} for p in PROVIDERS]


class MailboxBody(BaseModel):
    email: str
    password: str
    provider: Optional[str] = None
    host: Optional[str] = None
    port: int = 993
    username: Optional[str] = None
    # OpenAI(국외) 전송 동의. 동의 시각을 저장한다
    consented: bool = False


@app.post("/api/mailboxes")
def add_mailbox(body: MailboxBody, request: Request):
    user = _require_user(request)
    provider = get_provider(body.provider) if body.provider else detect_provider(body.email)
    if provider is None:
        raise HTTPException(400, "알 수 없는 메일 서비스입니다.")
    host = body.host or provider["host"]
    if not host:
        raise HTTPException(400, "IMAP 서버 주소를 입력해주세요.")
    username = body.username or body.email
    _login_check(Credential(body.email, host, body.port, username, body.password), provider)
    if not body.consented:
        raise HTTPException(400, "메일 분석 동의가 필요해요.")
    db.upsert_mailbox(user["id"], body.email, provider["id"], host, body.port, username, body.password, consented=True)
    return _me(user)


def _login_check(cred: Credential, provider: dict) -> None:
    # 서버 원문 오류(b'[AUTH] ...')는 사용자에게 보여주지 않고 로그에만 남긴다
    try:
        connect(cred).logout()
    except imaplib.IMAP4.error as e:
        print(f"[imap] login failed {cred.host}: {e}")
        raise HTTPException(401, f"로그인하지 못했어요. {provider['login_hint']}")
    except OSError as e:
        print(f"[imap] connect failed {cred.host}:{cred.port}: {e}")
        raise HTTPException(502, f"{cred.host}:{cred.port} 메일 서버에 연결하지 못했어요. 서버 주소와 포트를 확인해주세요.")


@app.delete("/api/mailboxes/{email}")
def remove_mailbox(email: str, request: Request):
    user = _require_user(request)
    db.delete_mailbox(user["id"], email)
    _running.pop((user["id"], email.lower()), None)
    return _me(user)


def _with_demo(report: dict, owner_email: str) -> dict:
    """보고서를 돌려주기 직전에 대신 처리 가능 여부를 지금 설정 기준으로 다시 정한다
    (검증된 흐름 또는 AI 탐색 모드). IDLY_DEMO=1이면 데모 계정도 맨 앞에 붙인다."""
    ai = _ai_agent_enabled()
    accounts = [
        {**a, "automatable": bool(supported_actions(a["id"])) or ai} for a in report.get("accounts", [])
    ]
    if os.getenv("IDLY_DEMO") == "1":
        accounts = [demo_account(owner_email)] + accounts
    return {**report, "accounts": accounts}


@app.get("/api/mailboxes/{email}/report")
def mailbox_report(email: str, request: Request):
    user = _require_user(request)
    report = db.get_report(user["id"], email)
    if report is None:
        raise HTTPException(404, "아직 탐색 결과가 없어요.")
    return _with_demo(report, email)


# --- 탐색 ---------------------------------------------------------------------------

class SyncBody(BaseModel):
    email: str
    # 폴더당 최근 몇 통까지 볼지. 기본은 상한까지 전부
    limit: int = MAX_PER_FOLDER


@app.post("/api/sync")
def sync(body: SyncBody, request: Request):
    user = _require_user(request)
    mailbox = db.get_mailbox(user["id"], body.email)
    if mailbox is None:
        raise HTTPException(404, "연동되지 않은 메일입니다.")
    if mailbox["secret"] is None:
        raise HTTPException(409, "저장된 로그인 정보를 읽지 못했어요. 메일을 다시 연동해주세요.")
    cred = Credential(mailbox["email"], mailbox["host"], mailbox["port"], mailbox["username"], mailbox["secret"])
    user_id, email = user["id"], mailbox["email"]
    job = start_sync(cred, max(1, min(body.limit, MAX_PER_FOLDER)), user_id,
                     on_done=lambda report: db.save_report(user_id, email, report))
    _running[(user_id, email)] = job.id
    return job.to_dict()


def _owned_job(request: Request, job_id: str) -> SyncJob:
    user = _require_user(request)
    job = get_job(job_id)
    if job is None or job.owner_id != user["id"]:
        raise HTTPException(404)
    return job


@app.get("/api/sync/{job_id}")
def sync_status(job_id: str, request: Request):
    return _owned_job(request, job_id).to_dict()


@app.get("/api/sync/{job_id}/report")
def sync_report(job_id: str, request: Request):
    job = _owned_job(request, job_id)
    if job.report is None:
        raise HTTPException(409, "아직 계정 탐색이 끝나지 않았습니다.")
    return _with_demo(job.report, job.email)


# --- 계정 조치 (에이전트) ------------------------------------------------------------
# runner=extension: 사용자 크롬의 IDly 확장이 조작 (기본, 로그인 정보가 브라우저를 떠나지 않음)
# runner=cloud:     서버의 클라우드 브라우저가 조작 (확장이 없을 때)

class ActionBody(BaseModel):
    domain: str
    service: str
    account_email: str
    action: str  # 탈퇴 | 구독 해지 | 권한 해제
    runner: str = "cloud"


@app.post("/api/actions")
def start_action(body: ActionBody, request: Request):
    """검증된 흐름 또는 AI 탐색 모드(키가 있을 때)로 대신 처리한다.
    둘 다 안 되면 422 → 프론트가 직접 처리 안내로 바꾼다."""
    user = _require_user(request)
    flow = find_flow(body.domain, body.action)
    user_id = user["id"]

    def on_event(event: str, detail: str) -> None:
        db.log_action(user_id, body.domain, body.account_email, body.action, event, detail)

    if body.runner == "extension":
        # 확장은 AI 탐색으로 진행한다 (데모 서비스도 같은 방식)
        if not _ai_agent_enabled():
            raise HTTPException(422, "확장 에이전트는 OpenAI API 키가 있어야 해요.")
        run = extension_runs.create(
            ExtensionRun(user_id, body.domain, body.action, body.service, body.account_email, on_event)
        )
        on_event("시작", "크롬 확장")
        # 확장이 이 작업 API를 부를 주소: 웹과 같은 출처(vite 프록시)를 쓴다
        return run.launch_info(str(request.base_url).rstrip("/"))

    if flow is None and not _ai_agent_enabled():
        raise HTTPException(422, f"{body.service} {body.action}은(는) 아직 대신 처리할 수 없어요.")
    run = start_run(ActionRun(user_id, body.domain, body.action, body.service, body.account_email, flow, on_event))
    return run.to_dict()


def _ai_agent_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _owned_run(request: Request, run_id: str):
    user = _require_user(request)
    run = get_run(run_id) or extension_runs.get(run_id)
    if run is None or run.owner_id != user["id"]:
        raise HTTPException(404)
    return run


@app.get("/api/actions")
def actions(request: Request):
    user = _require_user(request)
    runs = list_runs(user["id"]) + extension_runs.list_for(user["id"])
    return [r.to_dict() for r in runs]


@app.get("/api/actions/{run_id}")
def action_status(run_id: str, request: Request):
    return _owned_run(request, run_id).to_dict()


@app.get("/api/actions/{run_id}/screen")
def action_screen(run_id: str, request: Request):
    run = _owned_run(request, run_id)
    if getattr(run, "screen", None) is None:
        raise HTTPException(404)
    return Response(run.screen, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class ActionInput(BaseModel):
    # click(x, y) | type(text) | key(key) | scroll(dy) | resume | confirm | cancel
    type: str
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    dy: Optional[int] = None


_ALLOWED_KEYS = {"Enter", "Tab", "Backspace", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}


@app.post("/api/actions/{run_id}/input")
def action_input(run_id: str, body: ActionInput, request: Request):
    run = _owned_run(request, run_id)
    if body.type not in {"click", "type", "key", "scroll", "resume", "confirm", "cancel"}:
        raise HTTPException(400, "알 수 없는 입력입니다.")
    if body.type == "key" and body.key not in _ALLOWED_KEYS:
        raise HTTPException(400, "지원하지 않는 키입니다.")
    run.send(body.dict(exclude_none=True))
    return run.to_dict()


@app.get("/api/action-log")
def action_log(request: Request):
    user = _require_user(request)
    return db.list_actions(user["id"])


# --- 확장 전용 API (작업 토큰으로만) ---------------------------------------------------

def _ext_run(run_id: str, request: Request) -> ExtensionRun:
    run = extension_runs.by_token(run_id, request.headers.get("authorization", ""))
    if run is None:
        raise HTTPException(401, "작업 토큰이 올바르지 않거나 끝난 작업이에요.")
    return run


class AgentPage(BaseModel):
    url: str
    text: str = ""
    elements: list = []
    history: list = []
    step: int = 0


@app.post("/api/agent/{run_id}/decide")
def agent_decide(run_id: str, body: AgentPage, request: Request):
    """확장이 모은 화면 정보(버튼·링크 목록, 글자 일부)로 다음 행동을 정한다."""
    run = _ext_run(run_id, request)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(422, "OpenAI API 키가 없어요.")
    state = {"elements": body.elements[:150], "text": body.text[:2000]}
    try:
        return run.decide(api_key, body.url, state, [str(h)[:200] for h in body.history][-8:])
    except RuntimeError as e:
        raise HTTPException(502, str(e))


class AgentStatus(BaseModel):
    status: str
    message: str = ""
    step: int = 0
    error: Optional[str] = None


@app.post("/api/agent/{run_id}/status")
def agent_status(run_id: str, body: AgentStatus, request: Request):
    run = _ext_run(run_id, request)
    run.report(body.status, body.message, body.step, body.error)
    return {"ok": True}


@app.get("/api/agent/{run_id}/commands")
def agent_commands(run_id: str, request: Request):
    """웹(정리 내역)에서 누른 이어서 진행·확정·취소를 확장이 가져간다."""
    return {"commands": _ext_run(run_id, request).take_commands()}
