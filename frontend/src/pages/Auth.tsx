import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import { api } from '../api'

// IDly 계정 로그인·가입. 메일함은 로그인한 뒤 이 계정에 연동한다
export default function Auth() {
  const { applySession, startMock } = useStore()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const session = await (mode === 'login' ? api.login(email, password) : api.signup(email, password))
      applySession(session)
      // 연동한 메일이 없으면 첫 메일 연동부터
      navigate(session.mailboxes.length > 0 ? '/report' : '/add-mail')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-page">
      <div className="stack narrow">
        <div className="logo">IDly</div>
        <h1>내 계정, 한곳에서 확인하고 정리하세요</h1>
        <p className="muted">
          이메일에 흩어진 가입·인증·결제·로그인 기록으로 보유한 계정과 구독을 찾아내고, 필요 없는 계정의
          탈퇴·구독 해지·권한 해제까지 대신 처리합니다.
        </p>

        <div className="tabs">
          <button type="button" className={mode === 'login' ? 'tab active' : 'tab'} onClick={() => setMode('login')}>
            로그인
          </button>
          <button type="button" className={mode === 'signup' ? 'tab active' : 'tab'} onClick={() => setMode('signup')}>
            가입하기
          </button>
        </div>

        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span className="small muted">IDly 계정 이메일</span>
            <input type="email" autoComplete="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            <span className="small muted">비밀번호{mode === 'signup' && ' (8자 이상)'}</span>
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit" className="primary lg" disabled={busy || !email || password.length < (mode === 'signup' ? 8 : 1)}>
            {busy ? '확인 중…' : mode === 'login' ? '로그인' : '가입하고 메일 연동하기'}
          </button>
          {error && <div className="notice small">{error}</div>}
          {mode === 'signup' && (
            <p className="small muted">
              IDly 계정은 분석할 메일과 달라도 돼요. 가입한 뒤 여러 메일을 이 계정에 연동할 수 있어요.
            </p>
          )}
        </form>

        <div className="row between small muted">
          <span>첫 계정 현황 보고서와 계정 정리 1회는 무료예요.</span>
          <button
            type="button"
            className="link"
            onClick={() => {
              startMock()
              navigate('/scan')
            }}
          >
            로그인 없이 둘러보기
          </button>
        </div>
      </div>
    </div>
  )
}
