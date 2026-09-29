import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useStore } from "../store";
import { api, type Provider } from "../api";

// 로그인한 IDly 계정에 메일함을 연동한다 (IMAP 앱 비밀번호).
// 메일함이 하나도 없으면 첫 연동, 있으면 추가
export default function Connect() {
  const { applySession, mailboxes, user } = useStore();
  const navigate = useNavigate();
  const first = mailboxes.length === 0;
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [serverDown, setServerDown] = useState(false);
  const [email, setEmail] = useState("");
  // 자동 감지 결과를 사용자가 바꿨을 때만 값이 있다
  const [manualId, setManualId] = useState<string | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [password, setPassword] = useState("");
  const [host, setHost] = useState<string | null>(null);
  const [port, setPort] = useState("993");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .providers()
      .then(setProviders)
      .catch(() => setServerDown(true));
  }, []);

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const domain = validEmail ? email.split("@")[1].toLowerCase() : "";
  const detected = providers?.find((p) => p.domains.includes(domain));
  const provider = validEmail
    ? providers?.find((p) => p.id === (manualId ?? detected?.id ?? "custom"))
    : undefined;
  const isCustom = provider?.id === "custom";
  // OAuth는 쓰지 않는다. 비밀번호 IMAP을 막은 서비스(Outlook)는 아직 연동할 수 없다
  const unavailable = !!provider && !provider.auth.includes("password");
  // 모르는 도메인은 imap.<도메인>으로 먼저 채워 둔다
  const hostValue = host ?? (domain ? `imap.${domain}` : "");
  const alreadyAdded = mailboxes.some((m) => m.email.toLowerCase() === email.toLowerCase());

  const onEmail = (value: string) => {
    setEmail(value);
    setManualId(null);
    setChoosing(false);
    setHost(null);
    setError(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!provider || unavailable) return;
    setBusy(true);
    setError(null);
    try {
      const session = await api.addMailbox({
        email,
        password,
        provider: provider.id,
        consented: agreed,
        ...(isCustom ? { host: hostValue, port: Number(port) } : {}),
      });
      applySession(session);
      navigate(`/scan?mail=${encodeURIComponent(email.toLowerCase())}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-page">
      <div className="stack narrow">
        <div className="logo">IDly</div>
        <h1>{first ? "분석할 메일 연동" : "메일 추가"}</h1>
        <p className="muted">
          {first
            ? `${user?.email} 계정에 메일함을 연동하면 그 메일로 가입한 계정과 구독을 찾아요.`
            : "다른 메일로 가입한 계정도 함께 찾아요. 찾은 계정은 기존 보고서에 합쳐집니다."}
        </p>

        {serverDown ? (
          <div className="notice">
            <strong>IDly 서버에 연결할 수 없어요</strong>
            <div className="small">잠시 후 다시 시도해주세요.</div>
            <div className="row gap">
              <button onClick={() => window.location.reload()}>다시 시도</button>
            </div>
          </div>
        ) : (
          <form className="stack" onSubmit={submit}>
            <label className="field">
              <span className="small muted">연동할 메일 주소</span>
              <input
                type="email"
                autoComplete="email"
                autoFocus
                placeholder="me@naver.com"
                value={email}
                onChange={(e) => onEmail(e.target.value)}
              />
            </label>

            {provider && (
              <div className="small">
                {choosing ? (
                  <select
                    autoFocus
                    value={provider.id}
                    onChange={(e) => {
                      setManualId(e.target.value);
                      setChoosing(false);
                      setError(null);
                    }}
                    onBlur={() => setChoosing(false)}
                  >
                    {providers!.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="row gap">
                    <span>
                      {isCustom && !manualId
                        ? "자동으로 찾지 못한 메일이에요. IMAP 서버 정보를 확인해주세요."
                        : `${provider.name}로 연결합니다.`}
                    </span>
                    <button type="button" className="link" onClick={() => setChoosing(true)}>
                      다른 서비스 선택
                    </button>
                  </div>
                )}
              </div>
            )}

            {unavailable && (
              <div className="notice small">
                {provider!.name}는 앱 비밀번호 연동을 막아 두어 아직 연동할 수 없어요.
              </div>
            )}

            {provider && !unavailable && provider.steps.length > 0 && (
              <div className="notice small">
                <strong>먼저 {provider.name}에서 해주세요</strong>
                <ol className="steps">
                  {provider.steps.map((s) => (
                    <li key={s.text}>
                      {s.text}
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noreferrer">
                          열기 ↗
                        </a>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {provider && isCustom && (
              <div className="field-row">
                <label className="field">
                  <span className="small muted">IMAP 서버</span>
                  <input value={hostValue} onChange={(e) => setHost(e.target.value)} />
                </label>
                <label className="field">
                  <span className="small muted">포트</span>
                  <input type="number" value={port} onChange={(e) => setPort(e.target.value)} />
                </label>
              </div>
            )}

            {provider && !unavailable && (
              <>
                <label className="field">
                  <span className="small muted">{provider.password_label}</span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <span className="small muted">
                    암호화해서 저장하므로 다시 탐색할 때 다시 입력하지 않아도 돼요. 메일함을 빼면 지워요.
                  </span>
                </label>

                <label className="consent small">
                  <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
                  <span>
                    (필수) 계정 분석을 위해 주민번호·전화번호·인증번호·결제정보를 가린 메일 일부를
                    OpenAI(미국)로 보내는 데 동의합니다.
                  </span>
                </label>

                <button
                  type="submit"
                  className="primary lg"
                  disabled={busy || !agreed || !password || alreadyAdded || (isCustom && !hostValue)}
                >
                  {busy ? "연결 확인 중…" : "연결 확인하고 탐색 시작"}
                </button>
              </>
            )}

            {alreadyAdded && <div className="small muted">이미 연동한 메일이에요.</div>}
            {error && <div className="notice small">{error}</div>}
          </form>
        )}

        {!first && (
          <button type="button" className="link" onClick={() => navigate("/report")}>
            추가하지 않고 돌아가기
          </button>
        )}
      </div>
    </div>
  );
}
