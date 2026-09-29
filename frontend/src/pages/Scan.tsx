import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../store'
import { TOTAL_MAILS, type SignalType } from '../mock'

// 5칸 격자에 맞춰 대표 신호만 보여준다
const SIGNALS: SignalType[] = ['가입', '결제', '구독', '로그인', '보안']

// ?mail= 로 어떤 메일을 탐색할지 받는다. 없으면 첫 메일함
export default function Scan() {
  const { live, mailboxes, scanFor, startScan, accounts, removeMailbox } = useStore()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const email = params.get('mail') ?? mailboxes[0]?.email ?? ''

  useEffect(() => {
    startScan(email)
  }, [email])

  const { ratio, done, error, job, report } = scanFor(email)
  const total = live ? job?.total ?? 0 : TOTAL_MAILS
  const fetched = live ? job?.fetched ?? 0 : Math.round(TOTAL_MAILS * ratio)
  // live는 이 메일에서 찾은 계정만, 탐색이 끝나야 나온다. 목업은 진행 비율만큼 드러난다
  const found = live
    ? accounts.filter((a) => a.email === email)
    : accounts.slice(0, Math.round(accounts.length * ratio))
  const signalCounts = Object.fromEntries(
    SIGNALS.map((t) => [t, found.flatMap((a) => a.signals).filter((s) => s.type === t).length]),
  )

  const phase = !live
    ? null
    : job?.status === '분석 중'
      ? job.step === 'AI 판별'
        ? '계정 후보를 AI로 확인하는 중'
        : job.step === '결제 메일 확인'
          ? '구독 확인을 위해 결제 메일을 읽는 중'
          : '메일 헤더에서 계정 신호를 찾는 중'
      : job?.status === '완료' && !report
        ? '결과를 정리하는 중'
        : null

  return (
    <div className="center-page">
      <div className="stack narrow">
        <div className="logo">IDly</div>
        <h1>{done ? '계정 탐색이 끝났어요' : error ? '메일을 받지 못했어요' : '메일에서 계정을 찾고 있어요'}</h1>
        <p className="muted small">메일 양에 따라 몇 분에서 수십 분 걸릴 수 있어요.</p>

        <div>
          <div className="bar">
            <div className="bar-fill" style={{ transform: `scaleX(${ratio})` }} />
          </div>
          <div className="row between small muted">
            <span>
              {phase ?? `메일 ${fetched.toLocaleString()} / ${total ? total.toLocaleString() : '—'}`}
            </span>
            <span>{Math.round(ratio * 100)}%</span>
          </div>
        </div>

        {live && (
          <dl className="small">
            <dt>계정</dt>
            <dd>{email}</dd>
            <dt>폴더</dt>
            <dd>{job?.folders.length ? job.folders.join(', ') : '확인 중'}</dd>
            {report && (
              <>
                <dt>분석</dt>
                <dd>
                  메일 {report.messages_scanned.toLocaleString()}통 · 후보 {report.candidates}곳 ·{' '}
                  {report.ai_used
                    ? `AI 확인(${report.model})`
                    : report.ai_error
                      ? `규칙만 사용 (AI 실패: ${report.ai_error})`
                      : '규칙만 사용 (AI 키 없음)'}
                </dd>
              </>
            )}
          </dl>
        )}

        {(!live || done) && (
          <>
            <div className="stats">
              {SIGNALS.map((t) => (
                <div key={t} className="stat sm">
                  <div className="muted small">{t} 신호</div>
                  <div className="num">{signalCounts[t]}</div>
                </div>
              ))}
            </div>
            <div>
              <div className="section-title">발견한 계정 {found.length}개</div>
              <div className="chips">
                {found.map((a) => (
                  <span key={a.id} className="chip">
                    {a.service}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}

        {error && <div className="notice small">{error}</div>}

        {error ? (
          <button
            className="primary lg"
            onClick={() => {
              // 로그인 정보가 바뀌었을 수 있으니 이 메일함을 빼고 다시 연동
              removeMailbox(email)
              navigate('/add-mail')
            }}
          >
            다시 연동하기
          </button>
        ) : (
          <>
            <button className="primary lg" disabled={!done} onClick={() => navigate('/report')}>
              계정 현황 보고서 보기
            </button>
            {live && done && (
              <button className="link" onClick={() => startScan(email, true)}>
                새 메일까지 다시 탐색
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
