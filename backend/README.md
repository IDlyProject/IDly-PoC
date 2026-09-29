# IDly 웹 백엔드

웹 프론트엔드가 호출하는 백엔드. IDly 계정에 연동한 메일함에서 IMAP으로 메일 헤더를 받아 계정을 찾고,
검증된 흐름이 있는 서비스는 클라우드 브라우저 에이전트가 탈퇴·해지를 대신 처리한다.

- 메일 원문은 저장하지 않는다. 탐색 결과(계정 목록)만 저장한다.
- 메일 앱 비밀번호는 `IDLY_SECRET_KEY`로 암호화해 저장한다 (키를 잃으면 다시 연동해야 함).
- `OPENAI_API_KEY`는 백엔드 환경변수로만 둔다 (선택. 없으면 규칙만으로 분석).

## 처음 한 번만

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
# .env가 없을 때만 예제를 복사한다 (있으면 덮어쓰지 않음). 그다음 값을 채운다
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

## 실행 (매번)

```powershell
.\.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 47821
```

프론트는 `frontend`에서 `npm run dev` (개발 중 vite가 `/api`를 백엔드로 프록시).

## Render 배포

프론트(Vercel)는 `frontend/vercel.json`에서 `/api`를 이 서버로 리라이트한다.

- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt && PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium`
  - 크로미움을 패키지 폴더(.venv 안)에 받는다. 기본 위치(`/opt/render/.cache`)는 빌드 뒤 실행 환경에 남지 않는다.
    실행 중에는 `actions/runner.py`가 Render에서 같은 경로를 쓰고, 그래도 없으면 첫 작업 때 한 번 받는다
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- 환경변수 (`.env.example` 참고): `IDLY_SELF_URL=https://<서비스>.onrender.com`, `FORWARDED_ALLOW_IPS=*`

## IDly 계정과 메일함

- IDly 계정(이메일+비밀번호)으로 가입·로그인한다. 세션은 httpOnly 쿠키(`idly_session`), 30일.
- 메일함은 IDly 계정에 속한다: `POST /api/mailboxes`(연동, 동의 필수), `DELETE /api/mailboxes/{email}`.
- `GET /api/me`: 로그인한 계정, 연동한 메일함, 마지막 탐색 시각·진행 중 작업. 새로고침 뒤 프론트가 상태를 되살린다.
- 자기 계정의 메일·작업·결과만 볼 수 있다 (다른 계정은 401/404).
- 저장소: `DATABASE_URL`이 있으면 PostgreSQL(`idly` 스키마), 없으면 `data/idly.db`(SQLite).

## 계정 탐색 흐름

1. `POST /api/accounts`: IMAP 계정 연결 (로그인 확인)
2. `POST /api/sync`: 메일 헤더를 받고, 이어서 계정 탐색까지 백그라운드로 돈다
   - `GET /api/sync/{id}`: 상태 `받는 중` → `분석 중`(step: `헤더 분석` / `결제 메일 확인` / `AI 판별`) → `완료`
   - `GET /api/sync/{id}/report`: 찾은 계정 목록 (프론트 `Account` 구조)

수집 방식 (`imap_sync.py`)
- 폴더: 받은편지함 + 보관·사용자 폴더. 스팸·휴지통·보낸편지함·임시보관함은 제외. Gmail은 전체보관함 하나만.
- 개수: 폴더당 최근 10만 통까지(안전 상한) 헤더(`FROM SUBJECT DATE MESSAGE-ID`)만 500통씩 받는다. 폴더 간 중복은 Message-ID로 제거.
- 본문: 분석 중 서비스별 최근 결제 메일 1통만 앞부분 100KB를 받는다.

탐색 방식 (`analysis.py`)
1. 모든 헤더(보낸 곳·제목·날짜)를 규칙으로 훑어 신호를 고른다: 가입·인증·결제·구독·로그인·보안·안내.
   - 제외: 답장·전달, `(광고)`, 결제대행사(이니시스·KCP·토스페이먼츠 등), 광고·뉴스레터만 오는 곳, 지인 메일.
   - 구독 상태: 활성(정기결제) / 만료 예정 / 체험 종료 / 해지됨. 만료·해지는 제목에 구독·플랜·멤버십 같은 말이 있을 때만.
   - 안내: 휴면·미로그인·개인정보 파기·계정 삭제·데이터 백업 안내, 개인정보 이용내역 같은 회원 고지 (보안 알림으로 치지 않음).
2. 보낸 곳을 서비스 도메인 단위로 묶는다 (`mail.coupang.com` → `coupang.com`, `facebookmail.com` → `facebook.com`, `signin.aws` → AWS).
3. 서버 안에서만 본문을 읽는다 (외부 전송 없음, 키 없어도 동작)
   - 서비스별 최근 구독·결제 메일 1통: 금액(`결제금액 42,900 원`, `$20.00`), 다음 결제일(`다음 결제 예정일시 2026.10.20`)
   - 서비스별 최근 인증·로그인 메일 1통: "의심스러운 로그인 시도" 같은 문구가 있으면 같은 형식의 인증 메일을 보안 안내로 본다 (X 인증 코드 메일 등)
4. 키가 있으면 후보 서비스만 마스킹한 요약을 OpenAI로 보내 서비스 이름·분류·계정 여부를 다듬는다.
5. 결과: 계정 목록 + `insights`(메일로 확인한 상태 / IDly가 제안할 행동). 미사용·휴면+구독이면 구독 해지, 미사용·휴면이면 탈퇴를 추천.

OpenAI로 나가는 것: 도메인, 발신자 이름, 신호 메일 제목, 결제 메일 본문 일부 (주민번호·카드번호·전화번호·인증번호·이메일 아이디 마스킹).
개인정보 동의와 국외 이전 고지가 필요하다 (연동 화면에서 필수 동의로 받음).
메일로 알 수 없는 것: Google 연결 권한(항상 빈 값). 대신 처리 가능 여부는 검증된 에이전트 흐름이 있는 서비스만.

## 지원 메일 서비스

`providers.py` 참고. 앱 비밀번호 IMAP만 쓴다 (OAuth 없음).

| 서비스 | 방식 |
| --- | --- |
| Gmail, 네이버, 다음·한메일, 카카오, 네이트, iCloud, Yahoo, AOL, Zoho, GMX, Yandex, Fastmail | 앱 비밀번호 (또는 IMAP 허용된 계정 비밀번호) |
| Outlook / Hotmail / Live | 연동 불가 (Microsoft가 비밀번호 IMAP을 막음) |
| 기타 | IMAP 서버·포트 직접 입력 |

## 계정 정리 에이전트

### 크롬 확장 (기본)
사용자 크롬의 IDly 확장(`../extension`)이 새 탭에서 진행한다. 이미 로그인된 브라우저를 그대로 쓰고,
비밀번호·쿠키는 브라우저 밖으로 나가지 않는다. AI 판단(`OPENAI_API_KEY`)은 서버에서 한다.

- 설치(개발): `chrome://extensions` → 개발자 모드 → "압축해제된 확장 프로그램 로드" → `extension` 폴더
- 웹 ↔ 확장: `extension/bridge.js` (IDly 웹 출처에서만 동작, `manifest.json`의 `matches`). 운영 도메인이 생기면 추가
- 흐름: 웹이 `POST /api/actions {runner: "extension"}` → 작업 토큰·시작 주소를 확장에 전달 →
  확장이 매 단계 버튼·링크 목록을 `POST /api/agent/{id}/decide`로 보내 다음 행동을 받음 →
  상태는 `POST /api/agent/{id}/status`, 웹의 이어서 진행·확정·취소는 `GET /api/agent/{id}/commands`로 가져감
- 비밀번호 칸이 보이는 화면의 글자는 서버로 보내지 않고 사용자에게 로그인을 맡긴다 (로그인이 끝나면 자동으로 이어감)
- 되돌릴 수 없는 버튼은 서버가 규칙으로도 표시해 사용자 확정을 받는다 (작업 탭 패널 또는 웹 정리 내역)

### 클라우드 브라우저 (확장이 없을 때)
- 흐름 정의 `actions/flows.py`, 실행기 `actions/runner.py` (Playwright Chromium, 작업마다 새 시크릿 브라우저)
- 로그인·본인인증은 원격 화면으로 사용자가 직접, 탈퇴·해지 버튼 직전에는 사용자 확정
- `IDLY_DEMO=1`이면 보고서에 데모 서비스 계정이 나와 `/demo` 사이트에서 흐름을 끝까지 해볼 수 있다
- 실제 서비스 흐름은 실제 계정으로 확인한 뒤 `verified=True`로 추가한다
