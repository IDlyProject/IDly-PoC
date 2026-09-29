"""메일 헤더에서 온라인 계정을 찾는다.

1. 메일 헤더(보낸 곳·제목·날짜)만 규칙으로 훑어 계정 신호를 고른다. (AI 없음, 비용 없음)
   광고·답장·결제대행사 메일은 뺀다.
2. 보낸 곳을 서비스 도메인 단위로 묶고 가입일·최근 활동·구독 상태·휴면/삭제 안내·보안 알림을 정리한다.
3. 구독 메일은 본문을 이 서버 안에서만 읽어 금액·다음 결제일을 뽑는다. (외부 전송 없음)
4. OPENAI_API_KEY가 있으면 후보 서비스만 마스킹한 요약을 보내 서비스 이름·분류·계정 여부를 다듬는다.
5. 프론트엔드 Account 구조와 "메일로 확인한 상태 / IDly가 제안할 행동"(insights)으로 돌려준다.
"""

import html
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import httpx

from actions.flows import DEMO_DOMAIN, supported_actions

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AI_CHUNK = 30  # 한 번에 OpenAI로 보내는 서비스 수
UNUSED_DAYS = 365
RECENT_DAYS = 180  # 인증 메일 본문에서 의심 로그인 안내를 찾아볼 기간
USD_KRW = 1400  # 달러 결제를 원화로 대략 환산할 때

# --- 마스킹 -------------------------------------------------------------------

_EMAIL_LOCAL_RE = re.compile(r"\b[A-Z0-9._%+-]+@(?=[A-Z0-9.-]+\.[A-Z]{2,}\b)", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:01[016789][- ]?\d{3,4}[- ]?\d{4}|\+82[- ]?10[- ]?\d{3,4}[- ]?\d{4})(?!\d)")
_RESIDENT_RE = re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{1,7}(?!\d)")
# 인증번호는 '인증·코드·code' 근처 숫자만 가린다 (날짜·주문번호는 남긴다)
_OTP_RE = re.compile(r"((?:인증|코드|code|otp|verification|pin)[^\d\n]{0,20})\d{4,8}(?!\d)", re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.I | re.S)
_SPACE_RE = re.compile(r"\s+")


def redact(value: str) -> str:
    """메일이 서버 밖(OpenAI)으로 나가기 전에 직접 식별자를 가린다."""
    value = _RESIDENT_RE.sub("[주민번호]", value)
    value = _CARD_RE.sub("[카드번호]", value)
    value = _PHONE_RE.sub("[전화번호]", value)
    value = _OTP_RE.sub(r"\1[인증번호]", value)
    # 주소의 아이디만 가리고 도메인은 남긴다 (서비스를 알아보는 단서)
    return _EMAIL_LOCAL_RE.sub("[이메일]@", value)


# --- 1단계: 헤더 규칙 ---------------------------------------------------------

def _re(pattern: str) -> "re.Pattern[str]":
    return re.compile(pattern, re.I)


# 계정 신호로 보지 않는 제목: 답장·전달, 광고, 캘린더 초대, 비회원 주문
_SKIP_SUBJECT_RE = _re(
    r"^\s*(re|fw|fwd|답장|전달)\s*:|\(광고\)|\[광고\]|\d+\s?% off|할인 쿠폰|출시"
    r"|^\s*(초대|업데이트된 초대|invitation|updated invitation|accepted|수락됨|거절됨)\s*:|약속 예약됨|비회원"
)
# '휴면 해제'는 휴면이 풀렸다는 뜻 (다시 쓰기 시작한 계정)
_REACTIVATED_RE = _re(r"휴면\s?(해제|복구)|reactivat")

# 휴면·삭제·백업 안내 (계정이 곧 사라지거나 이미 방치된 상태)
# 백업은 계정·삭제 맥락이 있을 때만 (백업 방법을 알려주는 광고 제외)
_BACKUP_RE = _re(r"(back ?up|백업).{0,40}(account|계정|delet|삭제|days? left|기한)|(account|계정).{0,40}(back ?up|백업)|account data (attached|export)|days? left to back ?up")
_DORMANCY_RE = _re(r"미\s?로그인|휴면|장기\s?미(이용|사용|접속)|개인정보\s?파기|will be deleted|account.{0,30}(delet|clos)|inactive account|dormant|" + _BACKUP_RE.pattern)
# 인증·로그인 메일 본문에 이런 말이 있으면 본인이 아닌 로그인 시도 안내다
_SUSPICIOUS_BODY_RE = _re(r"의심스러운|suspicious|unusual (sign|activity|login)|누군가.{0,20}로그인|someone (tried|attempted)|본인이 로그인을 시도하셨나요")
# 회원에게만 오는 정기 고지 (계정이 있다는 신호일 뿐 보안 문제는 아님)
_MEMBER_NOTICE_RE = _re(r"개인정보\s?이용\s?내역|이용\s?내역\s?(통지|안내)|수신\s?동의.{0,10}(확인|안내)|약관.{0,6}(변경|개정)|개인정보\s?(처리)?\s?방침")

# 구독 상태. 구독 맥락 단어가 있어야 만료·해지로 본다 (스탬프 만료, 스토리 만료 같은 오탐 방지)
_SUB_CONTEXT_RE = _re(r"구독|멤버십|membership|subscription|플랜|plan|요금제|이용권|pro\b|premium|프리미엄")
_SUB_STATES: List[Tuple[str, "re.Pattern[str]", bool]] = [
    # (상태, 패턴, 구독 맥락 단어 필요 여부)
    ("해지됨", _re(r"갱신되지\s?않|해지.{0,4}(완료|되었|신청|접수)|cancel+ation|cancel+ed|won'?t renew|구독이 취소"), True),
    ("체험 종료", _re(r"trial.{0,10}(ended|has ended|expired|is over)|(무료\s?)?체험.{0,8}(종료|끝)|무료 플랜.{0,4}종료"), False),
    ("만료 예정", _re(r"만료(됩니다|예정|될|되기)|expir(es|ing)|ends on|곧 종료|갱신하세요|renew now"), True),
    ("활성", _re(r"정기\s?결제|자동\s?결제|구독.{0,10}(결제|갱신|완료|시작)|subscription.{0,25}(renew|confirm|receipt|payment|started|active)|renewal (receipt|confirmation)|멤버십.{0,10}(결제|갱신)|membership.{0,10}(renew|payment)|welcome to the .{0,20}plan|플랜.{0,6}(결제|시작)"), False),
]

_SECURITY_RE = _re(r"의심|suspicious|unusual|비정상|새로운\s?(기기|환경|위치)|new (device|sign-?in|login)|password (was )?(changed|reset)|비밀번호.{0,4}(변경|재설정)|유출|breach|security alert|보안\s?(경고|알림)")
# 보안 신호 중 사용자에게 '확인이 필요하다'고 알릴 것: 본인 확인을 묻거나 이상 징후를 알리는 안내만.
# "새 기기에서 로그인되었습니다" 같은 단순 통지는 신호로만 남기고 알리지 않는다
_SECURITY_ALERT_RE = _re(r"의심|suspicious|unusual|비정상|하셨나요|본인이 맞|was (this|it) you|password (was )?changed|비밀번호.{0,6}변경(되었|됐|됨)|유출|breach|(계정|account).{0,10}(정지|잠금|잠겼|suspend|lock)")

SIGNAL_PATTERNS = [
    ("가입", _re(r"가입|환영|welcome|sign[ -]?up|registration|계정이 (생성|만들어)|account (created|is ready)|getting started")),
    ("보안", _SECURITY_RE),
    ("결제", _re(r"결제|영수증|receipt|invoice|payment|청구|구매|주문|order|예약|booking|billing|charged")),
    ("로그인", _re(r"로그인|log[ -]?in|sign(ed)?[ -]?in|접속")),
    ("인증", _re(r"인증\s?(코드|번호)|인증 안내|이메일\s?인증|verif|confirm your|verification code|security code|login code|일회용 코드|one-?time|\botp\b|코드는|\bcode is\b")),
]

# 결제대행사: 결제 알림은 오지만 그 자체가 사용자의 서비스 계정은 아니다
PAYMENT_GATEWAYS = {
    "inicis.com", "kcp.co.kr", "tosspayments.com", "nicepay.co.kr", "danal.co.kr", "kakaopay.com",
    "cafe24corp.com", "payco.com", "settlebank.co.kr", "kicc.co.kr", "ksnet.co.kr", "paypal.com", "stripe.com",
}

# 사람끼리 주고받는 메일 도메인. 여기서 온 메일은 서비스 발신(noreply 등)일 때만 본다
FREEMAIL = {
    "gmail.com", "googlemail.com", "naver.com", "daum.net", "hanmail.net", "nate.com",
    "hotmail.com", "outlook.com", "live.com", "yahoo.com", "icloud.com", "me.com",
}
_SERVICE_SENDER_RE = _re(r"no-?reply|do-?not-?reply|notice|notification|account|security|info|help|support|mailer")

# 두 단계 최상위 도메인 (mail.coupang.co.kr → coupang.co.kr)
_MULTI_TLD = {
    "co.kr", "or.kr", "ne.kr", "go.kr", "ac.kr", "re.kr", "pe.kr",
    "co.jp", "ne.jp", "or.jp", "co.uk", "org.uk", "ac.uk",
    "com.au", "net.au", "com.cn", "com.tw", "com.sg", "com.br", "co.in",
}


# 한 서비스가 여러 도메인으로 메일을 보내는 경우
_DOMAIN_ALIASES = {
    "amazonaws.com": "aws.amazon.com", "aws.com": "aws.amazon.com", "twitter.com": "x.com",
    "claude.com": "anthropic.com", "clip-studio.com": "clipstudio.net", "smartthings.com": "samsung.com",
    "samsungcard.com": "samsungcard.com", "googlemail.com": "google.com", "accounts.google.com": "google.com",
}

# 자주 나오는 서비스의 이름·분류. AI 키가 없어도 이름과 분류가 제대로 나오게 한다
KNOWN_SERVICES: Dict[str, Tuple[str, str]] = {
    "coupang.com": ("쿠팡", "쇼핑"), "netflix.com": ("넷플릭스", "OTT"), "youtube.com": ("YouTube", "OTT"),
    "laftel.net": ("라프텔", "OTT"), "watcha.com": ("왓챠", "OTT"), "tving.com": ("티빙", "OTT"),
    "melon.com": ("멜론", "음악"), "spotify.com": ("Spotify", "음악"), "distrokid.com": ("DistroKid", "창작"),
    "bandlab.com": ("BandLab", "창작"), "beatstars.com": ("BeatStars", "창작"),
    "x.com": ("X", "SNS"), "facebook.com": ("Facebook", "SNS"), "instagram.com": ("Instagram", "SNS"),
    "pinterest.com": ("Pinterest", "SNS"), "snapchat.com": ("Snapchat", "SNS"), "band.us": ("밴드", "SNS"),
    "kakao.com": ("카카오", "SNS"), "kakaocorp.com": ("카카오", "SNS"), "cyworld.com": ("싸이월드", "SNS"),
    "google.com": ("Google", "생산성"), "microsoft.com": ("Microsoft", "생산성"), "apple.com": ("Apple", "생산성"),
    "notion.so": ("Notion", "생산성"), "zoom.us": ("Zoom", "생산성"), "hancom.com": ("한컴", "생산성"),
    "simplenote.com": ("Simplenote", "생산성"), "readdle.com": ("Spark", "생산성"), "streak.com": ("Streak", "생산성"),
    "any.do": ("Any.do", "생산성"), "dropbox.com": ("Dropbox", "클라우드"), "mediafire.com": ("MediaFire", "클라우드"),
    "sendanywhere.com": ("Send Anywhere", "클라우드"), "lastpass.com": ("LastPass", "생산성"),
    "openai.com": ("OpenAI", "생산성"), "anthropic.com": ("Anthropic(Claude)", "생산성"), "manus.im": ("Manus", "생산성"),
    "aws.amazon.com": ("AWS", "개발"), "snyk.io": ("Snyk", "개발"), "n8n.io": ("n8n", "개발"),
    "huggingface.co": ("Hugging Face", "개발"), "expo.dev": ("Expo", "개발"), "upstage.ai": ("Upstage", "개발"),
    "portswigger.net": ("PortSwigger", "개발"), "hackthebox.com": ("Hack The Box", "개발"), "yorba.co": ("Yorba", "생산성"),
    "wishket.com": ("위시켓", "커리어"), "saramin.co.kr": ("사람인", "커리어"), "linkedin.com": ("LinkedIn", "커리어"),
    "data-bank.ai": ("TestGlider", "교육"), "ets.org": ("TOEFL(ETS)", "교육"), "ebs.co.kr": ("EBS", "교육"),
    "nurimedia.co.kr": ("DBpia", "교육"), "dacon.io": ("데이콘", "교육"), "coursera.org": ("Coursera", "교육"),
    "inflearn.com": ("인프런", "교육"), "etoos.com": ("이투스", "교육"), "megastudy.net": ("메가스터디", "교육"),
    "multicampus.co.kr": ("멀티캠퍼스", "교육"), "riss.kr": ("RISS", "교육"), "edunet.net": ("에듀넷", "교육"),
    "by-works.com": ("AI 허브", "개발"), "ybmnet.co.kr": ("YBM NET", "교육"), "move.is": ("오르비", "교육"),
    "adobe.com": ("Adobe", "디자인"), "behance.net": ("Behance", "디자인"), "behance.com": ("Behance", "디자인"),
    "canva.com": ("Canva", "디자인"), "miricanvas.com": ("미리캔버스", "디자인"), "sandoll.co.kr": ("산돌구름", "디자인"),
    "clipstudio.net": ("CLIP STUDIO", "창작"), "pixiv.net": ("pixiv", "창작"), "postype.com": ("포스타입", "창작"),
    "capcut.com": ("CapCut", "창작"), "rawpixel.com": ("rawpixel", "디자인"), "pngtree.com": ("Pngtree", "디자인"),
    "tinkercad.com": ("Tinkercad", "디자인"), "prezi.com": ("Prezi", "생산성"), "typecast.ai": ("Typecast", "창작"),
    "nexon.com": ("넥슨", "게임"), "riotgames.com": ("라이엇게임즈", "게임"), "nintendo.com": ("Nintendo", "게임"),
    "twitch.tv": ("Twitch", "게임"), "ea.com": ("EA", "게임"), "netmarble.com": ("넷마블", "게임"),
    "smilegate.com": ("STOVE", "게임"), "onstove.com": ("STOVE", "게임"), "pokemon.com": ("Pokémon GO", "게임"),
    "nianticlabs.com": ("Pokémon GO", "게임"), "daum.net": ("다음", "SNS"),
    "interpark.com": ("인터파크", "여행"), "hotels.com": ("Hotels.com", "여행"), "marriott.com": ("Marriott", "여행"),
    "koreanair.com": ("대한항공", "여행"), "viarail.ca": ("VIA Rail", "여행"), "megabox.co.kr": ("메가박스", "기타"),
    "sejongpac.or.kr": ("세종문화회관", "기타"), "bucketplace.net": ("오늘의집", "쇼핑"), "aladin.co.kr": ("알라딘", "쇼핑"),
    "kaerumall.com": ("카에루몰", "쇼핑"), "ohprint.me": ("오프린트미", "쇼핑"), "redprinting.co.kr": ("레드프린팅", "쇼핑"),
    "snaps.com": ("스냅스", "쇼핑"), "bizhows.com": ("비즈하우스", "쇼핑"), "marpple.com": ("마플", "쇼핑"),
    "wish.com": ("Wish", "쇼핑"), "ebay.com": ("eBay", "쇼핑"), "nike.com": ("Nike", "쇼핑"), "mwave.co.kr": ("Mwave", "쇼핑"),
    "kakaostyle.com": ("지그재그", "쇼핑"), "hellomarket.com": ("헬로마켓", "쇼핑"), "musinsa.com": ("무신사", "쇼핑"),
    "tossbank.com": ("토스뱅크", "금융"), "toss.im": ("토스", "금융"), "samsung.com": ("삼성 계정", "기타"),
    "navercorp.com": ("네이버", "기타"), "naver.com": ("네이버", "기타"), "betterme.world": ("BetterMe", "기타"),
    "runtastic.com": ("adidas Runtastic", "기타"), "polar.com": ("Polar", "기타"), "opensurvey.io": ("오픈서베이", "기타"),
}


def base_domain(domain: str) -> str:
    parts = domain.lower().strip(".").split(".")
    if parts[-1] == "aws":  # signin.aws, signup.aws
        return "aws.amazon.com"
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_TLD:
        base = ".".join(parts[-3:])
    else:
        base = ".".join(parts[-2:])
    # 발송 전용 도메인을 본 도메인으로 (facebookmail.com, samsung-mail.com, email-marriott.com)
    name, _, suffix = base.partition(".")
    for pattern in (r"^(.+?)-?mail$", r"^e?mail-(.+)$"):
        m = re.match(pattern, name)
        if m and m.group(1) not in ("g", "hot", "e", ""):
            base = f"{m.group(1)}.{suffix}"
            break
    return _DOMAIN_ALIASES.get(base, base)


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _date(value: Optional[str]) -> Optional[date]:
    """메일 날짜를 서버 시간대 기준 날짜로 (UTC로 온 메일이 하루 앞당겨 보이지 않게)."""
    try:
        sent = parsedate_to_datetime(value or "")
        return (sent.astimezone() if sent.tzinfo else sent).date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def subscription_state(subject: str) -> Optional[str]:
    for state, pattern, needs_context in _SUB_STATES:
        if pattern.search(subject) and (not needs_context or _SUB_CONTEXT_RE.search(subject)):
            return state
    return None


def classify(subject: str) -> Optional[str]:
    """제목 하나를 신호 종류로 분류한다. 순서가 중요하다 (예: '미로그인'은 로그인이 아니다)."""
    if _SKIP_SUBJECT_RE.search(subject):
        return None
    if _REACTIVATED_RE.search(subject):
        return "로그인"
    if _DORMANCY_RE.search(subject) or _MEMBER_NOTICE_RE.search(subject):
        return "안내"
    if subscription_state(subject):
        return "구독"
    for kind, pattern in SIGNAL_PATTERNS:
        if pattern.search(subject):
            return kind
    return None


def _text_body(message: Message) -> str:
    parts: List[str] = []
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True) or b""
        content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            content = _HTML_RE.sub(" ", _STYLE_RE.sub(" ", content))
        # &#8202; 같은 문자 코드를 풀어야 그 안의 숫자가 금액·날짜로 잘못 읽히지 않는다
        parts.append(html.unescape(content))
    return _SPACE_RE.sub(" ", "\n".join(parts)).strip()


# --- 3단계: 구독 메일 본문에서 금액·다음 결제일 (서버 안에서만) --------------------

_AMOUNT_NEAR_RE = _re(r"(결제\s?금액|결제액|청구\s?금액|금액|합계|총액|total|amount|charged)[^\d₩$]{0,20}(₩|\$|US\$|KRW|USD)?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{2})?\s?(원)?")
_KRW_RE = _re(r"(?:₩|KRW)\s?(\d{1,3}(?:,\d{3})+|\d{3,})|(\d{1,3}(?:,\d{3})+)\s?원")
_USD_RE = _re(r"(?:US\$|\$|USD)\s?(\d+(?:\.\d{2})?)")
_NEXT_KO_RE = _re(r"(다음\s?(결제|청구|갱신)\s?(일|예정일|예정)?|결제\s?예정일)[^\d]{0,15}(?:(\d{4})\s*[.\-/년]\s*)?(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_NEXT_EN_RE = _re(r"(next (billing|payment|charge)( date)?|renews? on|will renew on)\W{0,5}([a-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})")


def parse_amount(text: str) -> Optional[int]:
    """본문에서 결제 금액(원)을 찾는다. 금액 근처 단어가 있는 숫자를 먼저 본다."""
    m = _AMOUNT_NEAR_RE.search(text)
    if m:
        value = float(m.group(3).replace(",", "") + (m.group(4) or ""))
        is_usd = (m.group(2) or "").upper() in {"$", "US$", "USD"}
        if value > 0:
            return int(round(value * USD_KRW)) if is_usd else int(value)
    m = _KRW_RE.search(text)
    if m:
        return int((m.group(1) or m.group(2)).replace(",", ""))
    m = _USD_RE.search(text)
    if m:
        return int(round(float(m.group(1)) * USD_KRW))
    return None


def parse_next_billing(text: str, sent: Optional[date]) -> Optional[str]:
    m = _NEXT_KO_RE.search(text)
    if m:
        year = int(m.group(4)) if m.group(4) else (sent.year if sent else datetime.now().year)
        try:
            found = date(year, int(m.group(5)), int(m.group(6)))
            if sent and not m.group(4) and found < sent:
                found = date(year + 1, found.month, found.day)
            return found.isoformat()
        except ValueError:
            return None
    m = _NEXT_EN_RE.search(text)
    if m and m.group(4).lower()[:3] in _MONTHS:
        try:
            return date(int(m.group(6)), _MONTHS[m.group(4).lower()[:3]], int(m.group(5))).isoformat()
        except ValueError:
            return None
    return None


# 메일 위치 (폴더, UID). 필요한 메일 본문을 나중에 받을 때 쓴다
MailRef = Tuple[str, str]


class HeaderRecord(NamedTuple):
    ref: MailRef
    sender_name: str
    sender_address: str
    subject: str
    date: Optional[date]


def header_record(ref: MailRef, headers: Message) -> HeaderRecord:
    name, address = parseaddr(_decode(headers.get("From")))
    return HeaderRecord(ref, name.strip(), address.lower(), _decode(headers.get("Subject")), _date(headers.get("Date")))


# --- 2단계: 서비스 단위로 묶기 --------------------------------------------------

class Event(NamedTuple):
    date: Optional[date]
    subject: str
    ref: MailRef


class ServiceGroup:
    def __init__(self, domain: str):
        self.domain = domain
        self.sender_names: Counter = Counter()
        self.first_seen: Optional[date] = None
        self.last_seen: Optional[date] = None
        self.signals: List[Dict[str, str]] = []
        self.subscription: List[Tuple[str, Event]] = []  # (상태, 메일)
        self.dormancy: List[Event] = []
        self.security: List[Event] = []
        self.auth: List[Event] = []  # 인증·로그인 메일 (본문에 의심 로그인 안내가 있는지 본다)
        self.suspicious_login = False
        self.last_payment: Optional[Event] = None

    def add(self, ref: MailRef, sender_name: str, subject: str, when: Optional[date]) -> None:
        if sender_name:
            self.sender_names[sender_name] += 1
        if when:
            self.first_seen = min(self.first_seen or when, when)
            self.last_seen = max(self.last_seen or when, when)
        kind = classify(subject)
        if kind is None:
            return
        self.signals.append({"date": when.isoformat() if when else "", "type": kind, "subject": subject[:200]})
        event = Event(when, subject, ref)
        if kind == "구독":
            self.subscription.append((subscription_state(subject) or "활성", event))
        if kind == "안내" and _DORMANCY_RE.search(subject):
            self.dormancy.append(event)
        if kind == "보안" and not re.search(r"정기", subject):
            self.security.append(event)
        if kind in ("인증", "로그인"):
            self.auth.append(event)
        if kind in ("결제", "구독") and when and (self.last_payment is None or when >= (self.last_payment.date or date.min)):
            self.last_payment = event

    def latest(self, *kinds: str) -> Optional[str]:
        dates = [s["date"] for s in self.signals if s["type"] in kinds and s["date"]]
        return max(dates) if dates else None

    def earliest(self, *kinds: str) -> Optional[str]:
        dates = [s["date"] for s in self.signals if s["type"] in kinds and s["date"]]
        return min(dates) if dates else None

    def latest_subscription(self) -> Optional[Tuple[str, Event]]:
        dated = [s for s in self.subscription if s[1].date]
        return max(dated, key=lambda s: s[1].date) if dated else None

    def merge(self, other: "ServiceGroup") -> None:
        """같은 서비스로 보이는 다른 도메인의 신호를 합친다 (BetterMe 여러 도메인 등)."""
        self.sender_names.update(other.sender_names)
        for d in (other.first_seen, other.last_seen):
            if d:
                self.first_seen = min(self.first_seen or d, d)
                self.last_seen = max(self.last_seen or d, d)
        self.signals += other.signals
        self.subscription += other.subscription
        self.dormancy += other.dormancy
        self.security += other.security
        self.auth += other.auth
        if other.last_payment and (self.last_payment is None or (other.last_payment.date or date.min) > (self.last_payment.date or date.min)):
            self.last_payment = other.last_payment


# --- 서비스 이름 ------------------------------------------------------------------

# 발신자 이름 꼬리말 (Team, 팀, Inc. 등)
_NAME_SUFFIX_RE = _re(
    r"(\s*[,|·\-–]\s*)?\b(team|staff|notifications?|support|official|systems|corporation|corp\.?|inc\.?|"
    r"international|co\.,?\s*ltd\.?|ltd\.?|llc|korea|한국)\s*$|\s*(계정\s?팀|팀|소식|알림|고객센터|주식회사|㈜|\(주\))\s*$"
)
_NAME_PREFIX_RE = _re(r"^\s*(the|official|\(주\)|㈜|주식회사)\s+")
_PERSON_KO_RE = re.compile(r"^[가-힣]{2,3}$")
_PERSON_EN_RE = re.compile(r"^[A-Z][a-z]+ [A-Z][a-z]+$|^[a-z]+( [a-z]+)?$")


def _domain_label(domain: str) -> str:
    return domain.split(".")[0].replace("-", " ").title()


def clean_sender_name(name: str, domain: str) -> Optional[str]:
    """발신자 이름을 서비스 이름으로 다듬는다. 사람 이름·메일 주소처럼 보이면 None."""
    name = name.strip().strip('"')
    if not name or "@" in name:
        return None
    # "Luke at QR Code Generator", "David from Drawboard", "seeun lee via TestFlight" → 뒤쪽이 서비스
    m = re.search(r"\b(?:at|from|via)\s+(.+)$", name, re.I)
    if m:
        name = m.group(1)
    name = name.split(" | ")[0]  # "사람인 | 신입공채" → "사람인"
    name = re.sub(r"\[([^\]]+)\]\s*\(.*\)", r"\1", name)  # "[MARPPLE](no-reply)" → "MARPPLE"
    name = re.sub(r"\s*\((?:no-?reply|noreply)\)", "", name, flags=re.I)
    for _ in range(2):
        name = _NAME_SUFFIX_RE.sub("", name).strip()
    name = _NAME_PREFIX_RE.sub("", name).strip()
    if not name:
        return None
    label = domain.split(".")[0].lower()
    looks_person = _PERSON_KO_RE.match(name) or _PERSON_EN_RE.match(name)
    # 사람 이름처럼 보여도 도메인과 겹치면 서비스 이름이다 (멜론·넥슨 같은 짧은 이름)
    if looks_person and label not in name.lower().replace(" ", "") and name.lower().replace(" ", "") not in label:
        return None
    return name


def service_name(group: ServiceGroup) -> str:
    if group.domain in KNOWN_SERVICES:
        return KNOWN_SERVICES[group.domain][0]
    for name, _ in group.sender_names.most_common():
        cleaned = clean_sender_name(name, group.domain)
        if cleaned:
            return cleaned
    return _domain_label(group.domain)


def _name_key(name: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", name.lower())


def merge_same_services(groups: Dict[str, ServiceGroup]) -> Dict[str, ServiceGroup]:
    """이름이 같거나 한쪽이 다른 쪽을 포함하는 서비스를 하나로 (CLIP STUDIO / CLIP STUDIO PAINT)."""
    merged: Dict[str, ServiceGroup] = {}
    keys: Dict[str, str] = {}  # 이름 키 -> 대표 도메인
    # 신호가 많은 도메인을 대표로
    for domain, group in sorted(groups.items(), key=lambda kv: -len(kv[1].signals)):
        key = _name_key(service_name(group))
        target = keys.get(key)
        if target is None and len(key) >= 5:
            target = next((d for k, d in keys.items() if len(k) >= 5 and (key.startswith(k) or k.startswith(key))), None)
        if target:
            merged[target].merge(group)
        else:
            merged[domain] = group
            keys[key] = domain
    return merged


def collect_groups(records: List[HeaderRecord], owner_email: str) -> Dict[str, ServiceGroup]:
    groups: Dict[str, ServiceGroup] = {}
    for r in records:
        if "@" not in r.sender_address or r.sender_address == owner_email.lower():
            continue
        local, sender_domain = r.sender_address.rsplit("@", 1)
        if sender_domain in FREEMAIL and not _SERVICE_SENDER_RE.search(local):
            continue
        domain = base_domain(sender_domain)
        if domain in PAYMENT_GATEWAYS:
            continue
        group = groups.setdefault(domain, ServiceGroup(domain))
        group.add(r.ref, r.sender_name, r.subject, r.date)
    # 광고·뉴스레터만 오는 곳은 계정 신호가 없으므로 뺀다
    return merge_same_services({d: g for d, g in groups.items() if g.signals})


# --- 4단계: OpenAI 판별 (선택) --------------------------------------------------

CATEGORIES = ["쇼핑", "OTT", "음악", "배달", "여행", "교육", "생산성", "개발", "클라우드", "커리어", "금융", "게임", "SNS", "디자인", "창작", "통신", "기타"]


def _ai_input(group: ServiceGroup, body: str) -> Dict[str, Any]:
    recent = sorted(group.signals, key=lambda s: s["date"], reverse=True)[:6]
    return {
        "domain": group.domain,
        "sender_names": [n for n, _ in group.sender_names.most_common(3)],
        "signals": [{"date": s["date"], "type": s["type"], "subject": redact(s["subject"])} for s in recent],
        "latest_payment_mail": redact(body)[:600],
    }


def ai_classify(items: List[Dict[str, Any]], api_key: str) -> Dict[str, Dict[str, Any]]:
    prompt = {
        "task": "각 domain에 대해 사용자가 그 서비스에 계정을 가지고 있는지, 서비스 이름·분류·유료 구독 여부를 판별합니다.",
        "rules": [
            "service: 한국 사용자에게 익숙한 서비스 이름. 발신 회사와 서비스가 다르면 서비스 이름 (예: data-bank.ai가 TestGlider 결제를 보내면 TestGlider).",
            f"category: {', '.join(CATEGORIES)} 중 하나.",
            "services는 이미 규칙으로 가입·로그인·결제·보안 등 계정 신호가 있는 곳만 골랐습니다. "
            "로그인 코드·휴면 안내·예약·결제 메일은 계정이 있다는 뜻이므로 is_account는 기본적으로 true입니다. "
            "신호가 명백히 광고·뉴스레터 문구이거나 사용자 계정과 무관할 때만 false.",
            "subscription: 반복 결제되는 유료 구독이 확실할 때만 {plan, monthly_krw}. monthly_krw는 월 금액(원, 정수), 외화면 대략 원화로 환산. 아니면 null.",
            "메일에 없는 사실은 추측하지 않습니다.",
            "반드시 {\"services\": [{domain, service, category, is_account, subscription}]} JSON만 반환합니다.",
        ],
        "services": items,
    }
    try:
        response = httpx.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": OPENAI_MODEL,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "You classify online accounts from email metadata. Return only valid JSON."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            },
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("OpenAI 서버에 연결하지 못했습니다.") from exc
    if response.status_code == 401:
        raise RuntimeError("OpenAI API 키가 올바르지 않아요 (401). .env의 OPENAI_API_KEY를 확인해주세요.")
    if response.status_code == 429:
        raise RuntimeError("OpenAI 사용 한도를 넘었어요 (429). 요금제·크레딧을 확인해주세요.")
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI 분석 요청이 실패했습니다. ({response.status_code})")
    try:
        services = json.loads(response.json()["choices"][0]["message"]["content"])["services"]
        return {s["domain"]: s for s in services if isinstance(s, dict) and "domain" in s}
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("OpenAI 분석 결과를 읽지 못했습니다.") from exc


# --- 5단계: 화면용 계정 구조 ----------------------------------------------------

def _template(subject: str) -> str:
    """'X 인증 코드는 fjcdwn8g입니다' → 'X 인증 코드는 입니다' (코드·숫자 부분을 지운 제목 형식)"""
    return re.sub(r"\S*\d\S*", "", subject).strip()


def _md(d: Optional[date]) -> str:
    if not d:
        return "날짜 미상"
    # 올해가 아니면 연도를 붙인다
    prefix = f"{d.year}년 " if d.year != datetime.now().year else ""
    return f"{prefix}{d.month}월 {d.day}일"


# '확인이 필요한 계정'에 올릴 기간 (오래된 안내는 이미 지나간 일이라 노이즈)
INSIGHT_DAYS = {"만료 예정": 60, "체험 종료": 60, "해지됨": 90, "활성": 60, "보안": 90, "휴면": 365}
# 활동이 이보다 오래 없으면 탈퇴를 추천한다 (1년은 '미사용' 표시만)
WITHDRAW_DAYS = 730


def _won(n: int) -> str:
    return f"₩{n:,}"


def build_subscription(group: ServiceGroup, body: str, ai: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    latest = group.latest_subscription()
    ai_sub = (ai or {}).get("subscription") if isinstance((ai or {}).get("subscription"), dict) else None
    if latest is None and ai_sub is None:
        return None
    state, event = latest if latest else ("활성", group.last_payment)
    amount = parse_amount(body) if body else None
    if amount is None and ai_sub and isinstance(ai_sub.get("monthly_krw"), (int, float)) and ai_sub["monthly_krw"] > 0:
        amount = int(ai_sub["monthly_krw"])
    next_billing = parse_next_billing(body, event.date if event else None) if body else None
    # 메일에 다음 결제일이 없으면 한 달 뒤로 추정하되, 이미 지난 날짜면 추정하지 않는다
    if next_billing is None and state == "활성" and event and event.date:
        guess = event.date + timedelta(days=30)
        next_billing = guess.isoformat() if guess >= datetime.now().date() else None
    return {
        "plan": str((ai_sub or {}).get("plan") or "구독"),
        "monthly": amount if state in ("활성", "만료 예정") else None,
        "nextBilling": next_billing if state == "활성" else None,
        "status": state,
        "lastEventDate": event.date.isoformat() if event and event.date else None,
        "lastEventSubject": event.subject if event else "",
    }


def build_insights(group: ServiceGroup, sub: Optional[Dict[str, Any]], today: date) -> List[Dict[str, str]]:
    """사용자가 붙여준 표처럼 '메일로 확인한 상태'와 'IDly가 제안할 행동'을 만든다."""
    insights: List[Dict[str, str]] = []

    def within(d: Optional[date], kind: str) -> bool:
        return d is not None and d >= today - timedelta(days=INSIGHT_DAYS[kind])

    sub_date = date.fromisoformat(sub["lastEventDate"]) if sub and sub["lastEventDate"] else None
    # 다음 결제일이 남아 있는 구독은 기간과 상관없이 올린다
    upcoming = bool(sub and sub["status"] == "활성" and sub["nextBilling"] and date.fromisoformat(sub["nextBilling"]) >= today)
    if sub and (upcoming or within(sub_date, sub["status"])):
        when = _md(sub_date)
        amount = f" {_won(sub['monthly'])}" if sub["monthly"] else ""
        if upcoming:
            insights.append({"kind": "구독", "date": sub["lastEventDate"],
                             "status": f"{when}{amount} 정기결제. 다음 결제 {_md(date.fromisoformat(sub['nextBilling']))} 예정.",
                             "advice": "계속 쓸지 확인하고, 원치 않으면 결제일 전에 구독 해지"})
        elif sub["status"] == "활성":
            insights.append({"kind": "구독", "date": sub["lastEventDate"],
                             "status": f"{when}{amount} 유료 플랜·결제 안내. 이후 결제 메일은 없어요.",
                             "advice": "지금도 구독 중인지 결제 내역에서 확인"})
        elif sub["status"] == "만료 예정":
            insights.append({"kind": "구독", "date": sub["lastEventDate"],
                             "status": f"{when} 구독 만료 예정 안내.",
                             "advice": "현재 만료·갱신 상태 확인 후, 필요할 때만 재구독"})
        elif sub["status"] == "체험 종료":
            insights.append({"kind": "구독", "date": sub["lastEventDate"],
                             "status": f"{when} 무료 체험 종료 안내.",
                             "advice": "유료로 자동 전환되지 않았는지 결제 수단 확인"})
        elif sub["status"] == "해지됨":
            insights.append({"kind": "구독", "date": sub["lastEventDate"],
                             "status": f"{when} 구독 해지·갱신 중단 안내.",
                             "advice": "더 쓰지 않는다면 계정 정리, 결제 수단 연결만 확인"})

    # 본인 확인을 묻거나 이상 징후를 알리는 안내만 (단순 '로그인되었습니다' 통지는 제외)
    alerts = [
        e for e in group.security
        if within(e.date, "보안") and (group.suspicious_login or _SECURITY_ALERT_RE.search(e.subject))
    ]
    if alerts:
        last = max(alerts, key=lambda e: e.date)
        repeat = f" 최근 {len(alerts)}번 반복됐어요." if len(alerts) > 1 else ""
        what = "의심스러운 로그인 시도 안내" if group.suspicious_login else f"보안 안내({last.subject[:50]})"
        insights.append({"kind": "보안", "date": last.date.isoformat(),
                         "status": f"{_md(last.date)} {what}.{repeat} 침해 성공의 증거는 아니에요.",
                         "advice": "본인 시도였는지 확인 → 아니라면 로그인 세션과 비밀번호 점검"})

    dormancy = [e for e in group.dormancy if within(e.date, "휴면")]
    if dormancy:
        last = max(dormancy, key=lambda e: e.date)
        backup = re.search(r"back ?up|백업|account data", last.subject, re.I)
        insights.append({"kind": "휴면", "date": last.date.isoformat() if last.date else "",
                         "status": f"{_md(last.date)} {'계정 데이터 백업·삭제' if backup else '장기 미사용·휴면'} 안내: {last.subject[:60]}",
                         "advice": "백업 파일 보관 여부와 현재 계정 상태 확인" if backup
                         else "유지할 계정인지 결정하고 현재 계정 상태 확인"})
    return insights


def to_account(group: ServiceGroup, ai: Optional[Dict[str, Any]], body: str, owner_email: str, today: date) -> Dict[str, Any]:
    last_activity = group.latest("로그인", "인증", "결제", "구독")
    last_login = group.latest("로그인", "인증")
    reference = last_activity or (group.last_seen.isoformat() if group.last_seen else None)
    idle_days = (today - date.fromisoformat(reference)).days if reference else None
    dormant_notice = any(e.date and e.date >= today - timedelta(days=INSIGHT_DAYS["휴면"]) for e in group.dormancy)
    unused = dormant_notice or (idle_days is not None and idle_days > UNUSED_DAYS)

    subscription = build_subscription(group, body, ai)
    insights = build_insights(group, subscription, today)
    security = next((i for i in insights if i["kind"] == "보안"), None)
    paying = subscription is not None and subscription["status"] in ("활성", "만료 예정")

    # 탈퇴 추천은 휴면·삭제 안내가 왔거나 2년 넘게 활동이 없을 때만 (1년은 '미사용' 표시만)
    if unused and paying:
        recommended = "구독 해지"
    elif dormant_notice or (idle_days is not None and idle_days > WITHDRAW_DAYS):
        recommended = "탈퇴"
    else:
        recommended = None

    known = KNOWN_SERVICES.get(group.domain)
    category = known[1] if known else (ai or {}).get("category")
    return {
        "id": group.domain,
        # 알려진 서비스 이름 > AI가 정한 이름 > 발신자 이름 정리
        "service": known[0] if known else ((ai or {}).get("service") or service_name(group)),
        "category": category if category in CATEGORIES else "기타",
        "email": owner_email,
        "signupDate": group.earliest("가입") or (group.first_seen.isoformat() if group.first_seen else ""),
        "lastLogin": last_login,
        "subscription": subscription,
        "unused": unused,
        "securityAlert": security["status"] if security else None,
        "insights": insights,
        # 연결 권한은 메일만으로 알 수 없어 비워 둔다
        "permissions": [],
        # 검증된 에이전트 흐름이 있는 서비스만 대신 처리할 수 있다 (actions/flows.py)
        "automatable": bool(supported_actions(group.domain)),
        "recommended": recommended,
        "signals": sorted(group.signals, key=lambda s: s["date"], reverse=True)[:10],
    }


def demo_account(owner_email: str) -> Dict[str, Any]:
    """IDLY_DEMO=1이면 보고서에 넣는 데모 서비스 계정. 에이전트 흐름을 화면에서 끝까지 해볼 수 있다."""
    today = datetime.now().date().isoformat()
    return {
        "id": DEMO_DOMAIN, "service": "데모 서비스 (에이전트 체험)", "category": "기타", "email": owner_email,
        "signupDate": today, "lastLogin": None, "subscription": None, "unused": True, "securityAlert": None,
        "insights": [], "permissions": [], "automatable": True, "recommended": "탈퇴",
        "signals": [{"date": today, "type": "가입", "subject": "데모 서비스 가입을 환영합니다"}],
    }


def discover_accounts(
    records: List[HeaderRecord],
    owner_email: str,
    fetch_body: Callable[[MailRef], Optional[Message]],
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    report = on_progress or (lambda _: None)
    report("헤더 분석")
    groups = collect_groups(records, owner_email)

    # 구독·결제 메일 본문은 서버 안에서만 읽는다 (금액·다음 결제일)
    report("결제 메일 확인")
    bodies: Dict[str, str] = {}
    for d, g in groups.items():
        latest = g.latest_subscription()
        event = latest[1] if latest else g.last_payment
        if event is None:
            continue
        try:
            message = fetch_body(event.ref)
            bodies[d] = _text_body(message) if message else ""
        except Exception:
            bodies[d] = ""

    # 인증 코드 메일은 제목만으로는 모른다. 최근 것 1통의 본문에 의심 로그인 안내가 있으면
    # 같은 형식의 최근 인증 메일을 모두 보안 안내로 본다 (X 등)
    report("보안 메일 확인")
    recent = datetime.now().date() - timedelta(days=RECENT_DAYS)
    for g in groups.values():
        auth = [e for e in g.auth if e.date and e.date >= recent]
        if not auth:
            continue
        latest = max(auth, key=lambda e: e.date)
        try:
            message = fetch_body(latest.ref)
            text = _text_body(message)[:1500] if message else ""
        except Exception:
            text = ""
        if _SUSPICIOUS_BODY_RE.search(text):
            g.suspicious_login = True
            template = _template(latest.subject)
            g.security.extend(e for e in auth if _template(e.subject) == template)

    ai_results: Dict[str, Dict[str, Any]] = {}
    ai_error: Optional[str] = None
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key and groups:
        report("AI 판별")
        items = [_ai_input(g, bodies.get(d, "")) for d, g in groups.items()]
        # AI가 실패해도(키 오류·한도 초과 등) 탐색 전체를 실패시키지 않고 규칙 결과로 보고서를 낸다
        try:
            for i in range(0, len(items), AI_CHUNK):
                ai_results.update(ai_classify(items[i:i + AI_CHUNK], api_key))
        except RuntimeError as e:
            ai_error = str(e)
            print(f"[analysis] AI 판별 실패, 규칙 결과만 사용: {e}")

    today = datetime.now().date()
    accounts = [
        to_account(g, ai_results.get(d), bodies.get(d, ""), owner_email, today)
        for d, g in groups.items()
        if ai_results.get(d, {}).get("is_account", True) is not False
    ]
    # 확인할 것이 있는 계정을 먼저
    accounts.sort(key=lambda a: (not a["insights"], a["subscription"] is None, not a["unused"], a["service"]))
    return {
        "messages_scanned": len(records),
        "candidates": len(groups),
        "ai_used": bool(ai_results),
        "ai_error": ai_error,
        "model": OPENAI_MODEL if ai_results else None,
        "accounts": accounts,
    }
