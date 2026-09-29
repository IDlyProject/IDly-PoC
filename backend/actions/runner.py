"""클라우드 브라우저 실행기. 흐름(flows.py)을 한 단계씩 실행한다.

- 작업마다 새 시크릿 브라우저 컨텍스트를 쓰고, 끝나면 폐기한다 (쿠키·세션 저장 안 함).
- DOM(글자·선택자)으로 먼저 찾고, 못 찾으면 OPENAI_API_KEY가 있을 때만 스크린샷으로 위치를 묻는다.
  그래도 못 찾으면 사용자에게 원격 화면을 넘긴다.
- 로그인·본인인증(user 단계)과 되돌릴 수 없는 버튼 직전(confirm 단계)에서는 반드시 멈춘다.
- Playwright sync API는 만든 스레드에서만 쓸 수 있어서, 원격 입력은 큐로 받아 작업 스레드가 처리한다.
"""

import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import httpx

from .flows import Flow, Step

VIEWPORT = {"width": 1280, "height": 800}
FIND_TIMEOUT_MS = 8000
USER_TIMEOUT_SEC = 15 * 60  # 사용자 입력을 이만큼 기다려도 없으면 실패로 끝낸다
SCREEN_INTERVAL_SEC = 0.7

# Render는 빌드 때 받은 ~/.cache를 실행 환경에 남기지 않는다. 브라우저를 패키지 폴더(.venv 안)에 두게 한다.
if os.getenv("RENDER"):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

_install_lock = threading.Lock()


def _launch(p):
    """크로미움이 설치돼 있지 않으면 한 번 받아서 다시 띄운다 (빌드 단계에서 설치를 빠뜨린 배포 대비)."""
    try:
        return p.chromium.launch(headless=True)
    except Exception as e:
        if "Executable doesn't exist" not in str(e):
            raise
    with _install_lock:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       check=True, capture_output=True, timeout=600)
    return p.chromium.launch(headless=True)

# 화면에 보이는 상태 (프론트 JobStatus와 같음)
QUEUED, RUNNING, NEEDS_INPUT, NEEDS_CONFIRM, DONE, FAILED, CANCELLED = (
    "대기", "진행 중", "입력 필요", "확인 필요", "완료", "실패", "취소됨",
)


class Cancelled(Exception):
    pass


class ActionRun:
    """flow가 있으면 정해진 흐름대로, 없으면 AI 탐색 모드(ai_agent.py)로 진행한다."""

    def __init__(self, owner_id: int, domain: str, action: str, service: str, account_email: str,
                 flow: Optional[Flow] = None, on_event: Optional[Callable[[str, str], None]] = None):
        self.id = uuid.uuid4().hex
        self.owner_id = owner_id
        self.domain = domain
        self.action = action
        self.flow = flow
        self.mode = "flow" if flow else "ai"
        self.service = service
        self.account_email = account_email
        self.status = QUEUED
        self.step_index = 0
        self.message = ""
        self.error: Optional[str] = None
        self.screen: Optional[bytes] = None
        self._commands: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._on_event = on_event or (lambda event, detail: None)

    def to_dict(self) -> dict:
        from .ai_agent import MAX_STEPS

        return {
            "id": self.id,
            "service": self.service,
            "domain": self.domain,
            "action": self.action,
            "mode": self.mode,
            "status": self.status,
            "step": self.step_index + 1,
            "steps": len(self.flow.steps) if self.flow else MAX_STEPS,
            "message": self.message,
            "error": self.error,
            "hasScreen": self.screen is not None,
        }

    def event(self, name: str, detail: str = "") -> None:
        self._on_event(name, detail)

    # --- API가 부르는 쪽 (다른 스레드) ---

    def send(self, command: Dict[str, Any]) -> None:
        self._commands.put(command)

    # --- 작업 스레드 ---

    def run(self) -> None:
        from playwright.sync_api import sync_playwright

        self.status = RUNNING
        self._on_event("시작", "")
        self.message = "브라우저를 준비하고 있어요"
        try:
            with sync_playwright() as p:
                browser = _launch(p)
                context = browser.new_context(viewport=VIEWPORT, locale="ko-KR")
                page = context.new_page()
                try:
                    if self.flow:
                        for i, step in enumerate(self.flow.steps):
                            self.step_index = i
                            self.message = step.label
                            self._do(page, step)
                            self._snap(page)
                    else:
                        from .ai_agent import run_goal

                        run_goal(self, page)
                    self.status = DONE
                    self.message = "완료했어요"
                    self._on_event("완료", "")
                finally:
                    context.close()
                    browser.close()
        except Cancelled:
            self.status = CANCELLED
            self.message = "취소했어요"
            self._on_event("취소", "")
        except Exception as e:
            self.status = FAILED
            self.error = str(e).splitlines()[0][:200]
            self.message = "진행하지 못했어요"
            self._on_event("실패", self.error)

    def _do(self, page, step: Step) -> None:
        if step.kind == "goto":
            page.goto(step.url, wait_until="domcontentloaded")
        elif step.kind == "click":
            if not self._click(page, step):
                self._wait_user(page, f"화면이 예상과 달라요. '{step.label}'을(를) 직접 눌러 주세요.")
        elif step.kind == "fill":
            page.locator(step.selector).first.fill(step.value or "", timeout=FIND_TIMEOUT_MS)
        elif step.kind == "user":
            self._wait_user(page, step.label, until_text=step.until_text, until_url=step.until_url)
        elif step.kind == "confirm":
            self._wait_confirm(page, step.label)
        elif step.kind == "expect":
            page.get_by_text(step.text).first.wait_for(state="visible", timeout=FIND_TIMEOUT_MS * 2)
        else:
            raise ValueError(f"알 수 없는 단계: {step.kind}")

    def _click(self, page, step: Step) -> bool:
        """DOM으로 찾아 클릭. 없으면 AI 스크린샷 보조."""
        candidates = []
        if step.selector:
            candidates.append(page.locator(step.selector))
        if step.text:
            candidates += [
                page.get_by_role("button", name=step.text),
                page.get_by_role("link", name=step.text),
                page.get_by_text(step.text, exact=False),
            ]
        deadline = time.time() + FIND_TIMEOUT_MS / 1000
        while time.time() < deadline:
            for locator in candidates:
                target = locator.first
                if target.count() and target.is_visible():
                    target.click()
                    page.wait_for_load_state("domcontentloaded")
                    return True
            self._drain(page)
            time.sleep(0.3)
        return self._ai_click(page, step)

    def _ai_click(self, page, step: Step) -> bool:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return False
        shot = page.screenshot()
        prompt = (
            f"이 웹페이지 스크린샷({VIEWPORT['width']}x{VIEWPORT['height']})에서 '{step.text or step.label}'에 해당하는 "
            "버튼이나 링크의 중심 좌표를 찾아주세요. 확실하지 않으면 found=false. "
            'JSON만: {"found": true|false, "x": 정수, "y": 정수}'
        )
        try:
            res = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(shot).decode()}},
                    ]}],
                },
                timeout=60,
            )
            answer = json.loads(res.json()["choices"][0]["message"]["content"])
        except Exception:
            return False
        if not answer.get("found"):
            return False
        page.mouse.click(int(answer["x"]), int(answer["y"]))
        page.wait_for_load_state("domcontentloaded")
        self._on_event("AI 보조 클릭", step.label)
        return True

    def _wait_user(self, page, reason: str, until_text: Optional[str] = None, until_url: Optional[str] = None) -> None:
        """원격 화면을 넘기고, 조건이 보이거나 사용자가 '이어서 진행'을 누를 때까지 기다린다."""
        self.status = NEEDS_INPUT
        self.message = reason
        self._on_event("사용자 입력 요청", reason)
        started = time.time()
        while time.time() - started < USER_TIMEOUT_SEC:
            if self._drain(page, allow={"resume"}) == "resume":
                break
            if until_url and until_url in page.url:
                break
            if until_text and page.get_by_text(until_text).first.is_visible():
                break
            time.sleep(SCREEN_INTERVAL_SEC)
        else:
            raise TimeoutError("사용자 입력을 기다리다 시간이 지났어요.")
        self.status = RUNNING

    def _wait_confirm(self, page, reason: str) -> None:
        self.status = NEEDS_CONFIRM
        self.message = reason
        self._on_event("최종 확인 요청", reason)
        started = time.time()
        while time.time() - started < USER_TIMEOUT_SEC:
            if self._drain(page, allow={"confirm"}) == "confirm":
                self._on_event("사용자 확정", "")
                self.status = RUNNING
                return
            time.sleep(SCREEN_INTERVAL_SEC)
        raise TimeoutError("확정을 기다리다 시간이 지났어요.")

    def _drain(self, page, allow: frozenset = frozenset()) -> Optional[str]:
        """쌓인 원격 입력을 처리하고 화면을 새로 찍는다. 흐름 제어 명령(resume/confirm)이 오면 돌려준다."""
        result = None
        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                break
            kind = cmd.get("type")
            if kind == "cancel":
                raise Cancelled()
            if kind in allow:
                result = kind
            elif kind == "click":
                page.mouse.click(int(cmd["x"]), int(cmd["y"]))
            elif kind == "type":
                page.keyboard.type(str(cmd.get("text", "")), delay=20)
            elif kind == "key":
                page.keyboard.press(str(cmd.get("key", "Enter")))
            elif kind == "scroll":
                page.mouse.wheel(0, int(cmd.get("dy", 400)))
        self._snap(page)
        return result

    def _snap(self, page) -> None:
        try:
            self.screen = page.screenshot(type="jpeg", quality=70)
        except Exception:
            pass


_runs: Dict[str, ActionRun] = {}


def start_run(run: ActionRun) -> ActionRun:
    _runs[run.id] = run
    threading.Thread(target=run.run, daemon=True).start()
    return run


def get_run(run_id: str) -> Optional[ActionRun]:
    return _runs.get(run_id)


def list_runs(owner_id: int) -> List[ActionRun]:
    return [r for r in _runs.values() if r.owner_id == owner_id]
