import { useEffect, useState, type FormEvent, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { manualSteps, useStore, type Job, type JobStatus } from '../store'
import { api } from '../api'

const ORDER: JobStatus[] = ['입력 필요', '확인 필요', '직접 처리', '진행 중', '대기', '완료']
const NEEDS_USER: JobStatus[] = ['입력 필요', '확인 필요', '직접 처리']

export default function Progress() {
  const { jobs, accounts } = useStore()
  const navigate = useNavigate()

  if (jobs.length === 0) {
    return (
      <div className="page">
        <h1>정리 내역</h1>
        <div className="empty-box">
          <p>아직 정리한 계정이 없습니다.</p>
          <button onClick={() => navigate('/report')}>계정 현황 보기</button>
        </div>
      </div>
    )
  }

  const serviceOf = (j: Job) => accounts.find((a) => a.id === j.accountId)?.service ?? j.accountId
  const todo = jobs.filter((j) => NEEDS_USER.includes(j.status))
  const sorted = [...jobs].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status))
  const counts: [string, number][] = [
    ['내가 할 일', todo.length],
    ['진행 중', jobs.filter((j) => j.status === '진행 중').length],
    ['대기', jobs.filter((j) => j.status === '대기').length],
    ['완료', jobs.filter((j) => j.status === '완료').length],
    ['전체', jobs.length],
  ]

  return (
    <div className="page">
      <header>
        <h1>정리 내역</h1>
        <div className="muted small">IDly가 순서대로 진행합니다. 로그인·본인인증·탈퇴 확정처럼 직접 해야 하는 단계만 여기에 모아 드려요.</div>
      </header>

      <div className="stats">
        {counts.map(([label, n]) => (
          <div key={label} className="stat sm">
            <div className="muted small">{label}</div>
            <div className="num">{n}</div>
          </div>
        ))}
      </div>

      {todo.length > 0 && (
        <section className="stack">
          <div className="section-title">지금 할 일</div>
          {todo.map((j) => (
            <TodoCard key={j.id} job={j} service={serviceOf(j)} />
          ))}
        </section>
      )}

      <section>
        <div className="section-title">전체 내역</div>
        <table>
          <colgroup>
            <col style={{ width: 180 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 120 }} />
            <col />
            <col style={{ width: 100 }} />
          </colgroup>
          <thead>
            <tr>
              <th>서비스</th>
              <th>정리 방식</th>
              <th>상태</th>
              <th>메모</th>
              <th className="right">이용권</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((j) => (
              <tr key={j.id}>
                <td>{serviceOf(j)}</td>
                <td>{j.action}</td>
                <td>
                  <span className={NEEDS_USER.includes(j.status) ? 'tag strong' : 'tag'}>{j.status}</span>
                </td>
                <td className="muted small">{j.note ?? ''}</td>
                <td className="right small">{j.charged ? '1회' : '무료'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

// 클라우드 브라우저 화면. 1초마다 새로 받고, interactive면 클릭·글자·키를 그대로 전달한다
function RemoteScreen({ job, interactive = false }: { job: Job; interactive?: boolean }) {
  const { sendInput } = useStore()
  const [tick, setTick] = useState(0)
  const [text, setText] = useState('')

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  const click = (e: MouseEvent<HTMLImageElement>) => {
    if (!interactive) return
    const img = e.currentTarget
    const rect = img.getBoundingClientRect()
    // 화면에 줄여 보이는 크기 → 실제 브라우저 크기로 좌표 변환
    const x = Math.round(((e.clientX - rect.left) / rect.width) * img.naturalWidth)
    const y = Math.round(((e.clientY - rect.top) / rect.height) * img.naturalHeight)
    sendInput(job.id, { type: 'click', x, y })
  }

  const sendText = (e: FormEvent) => {
    e.preventDefault()
    if (!text) return
    sendInput(job.id, { type: 'type', text })
    setText('')
  }

  return (
    <div className="remote">
      <img
        src={api.actionScreenUrl(job.runId!, tick)}
        alt="원격 브라우저 화면"
        className={interactive ? 'remote-screen interactive' : 'remote-screen'}
        onClick={click}
      />
      {interactive && (
        <form className="row gap wrap" onSubmit={sendText}>
          <input
            placeholder="화면에서 입력칸을 누른 뒤 여기에 입력"
            value={text}
            onChange={(e) => setText(e.target.value)}
            autoComplete="off"
          />
          <button type="submit">입력</button>
          {['Enter', 'Tab', 'Backspace'].map((key) => (
            <button key={key} type="button" onClick={() => sendInput(job.id, { type: 'key', key })}>
              {key}
            </button>
          ))}
          <button type="button" onClick={() => sendInput(job.id, { type: 'scroll', dy: 400 })}>
            아래로
          </button>
        </form>
      )}
    </div>
  )
}

// 확장 작업은 사용자 크롬의 탭에서 진행된다. 원격 화면 대신 그 탭으로 보내는 버튼
function ExtensionTab({ job }: { job: Job }) {
  const { focusJobTab } = useStore()
  return (
    <div className="row gap small">
      <span className="muted">크롬의 새 탭에서 IDly 확장이 진행 중이에요. 탭 오른쪽 아래 패널에서도 확정·취소할 수 있어요.</span>
      <button onClick={() => focusJobTab(job.id)}>진행 중인 탭 열기</button>
    </div>
  )
}

function TodoCard({ job, service }: { job: Job; service: string }) {
  const { accounts, confirmJob, resolveInput, markManualDone, switchToManual, cancelJob } = useStore()
  const account = accounts.find((a) => a.id === job.accountId)

  if (job.status === '입력 필요') {
    return (
      <div className="notice">
        <div className="row between">
          <strong>
            {service} · {job.action}
          </strong>
          <span className="tag strong">입력 필요</span>
        </div>
        {job.mode === 'extension' ? (
          <>
            <div className="small">{job.note} 비밀번호는 IDly로 전달되지 않고 그 탭에서만 입력돼요.</div>
            <ExtensionTab job={job} />
          </>
        ) : (
          <div className="small">{job.note}. 아래 화면에서 직접 입력하면 IDly가 이어서 진행해요.</div>
        )}
        {job.mode === 'extension' ? null : job.runId ? (
          <RemoteScreen job={job} interactive />
        ) : (
          <div className="ph" style={{ height: 220 }}>
            원격 브라우저 화면 ({service})
          </div>
        )}
        <div className="row gap">
          <button className="primary" onClick={() => resolveInput(job.id)}>
            입력 완료, 이어서 진행
          </button>
          <button onClick={() => switchToManual(job.id)}>직접 처리로 바꾸기 (이용권 환불)</button>
        </div>
      </div>
    )
  }

  if (job.status === '확인 필요') {
    return (
      <div className="notice">
        <div className="row between">
          <strong>
            {service} · {job.action}
          </strong>
          <span className="tag strong">최종 확인</span>
        </div>
        <div className="small">{job.note}</div>
        {job.mode === 'extension' ? <ExtensionTab job={job} /> : job.runId && <RemoteScreen job={job} />}
        <div className="row gap">
          <button className="primary" onClick={() => confirmJob(job.id)}>
            {job.action} 확정
          </button>
          <button onClick={() => cancelJob(job.id)}>{job.action} 취소 (이용권 환불)</button>
        </div>
      </div>
    )
  }

  return (
    <div className="notice">
      <div className="row between">
        <strong>
          {service} · {job.action}
        </strong>
        <span className="tag strong">직접 처리</span>
      </div>
      {account && (
        <ol className="guide small">
          {manualSteps(account, job.action).map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      )}
      <div className="row gap">
        <button className="primary" onClick={() => markManualDone(job.id)}>
          처리했어요
        </button>
        <a
          href={`https://www.google.com/search?q=${encodeURIComponent(`${service} ${job.action}`)}`}
          target="_blank"
          rel="noreferrer"
          className="small"
        >
          더 자세한 방법 찾기
        </a>
      </div>
    </div>
  )
}
