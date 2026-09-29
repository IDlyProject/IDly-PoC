import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { availableActions, defaultAction, isPaying, monthlyOf, useStore, won } from '../store'
import { TOTAL_MAILS, type Account, type Insight } from '../mock'

const INSIGHT_KINDS: Insight['kind'][] = ['구독', '보안', '휴면']

type Filter = '전체' | '구독' | '미사용' | '보안' | '연결 권한'

const FILTERS: Record<Filter, (a: Account) => boolean> = {
  전체: () => true,
  구독: (a) => !!a.subscription,
  미사용: (a) => a.unused,
  보안: (a) => !!a.securityAlert,
  '연결 권한': (a) => a.permissions.length > 0,
}

export default function Report() {
  const { accounts, selected, select, unselect, dismissed, restoreDismissed, live, mailboxes } = useStore()
  const scannedMails = live ? mailboxes.reduce((sum, m) => sum + (m.report?.messages_scanned ?? 0), 0) : TOTAL_MAILS
  const multiMail = mailboxes.length > 1
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('전체')
  const [query, setQuery] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  // 급한 구독·보안은 펼쳐 두고, 개수가 많은 휴면은 접어 둔다
  const [openKinds, setOpenKinds] = useState<Insight['kind'][]>(['구독', '보안'])

  const rows = accounts.filter((a) => FILTERS[filter](a) && a.service.toLowerCase().includes(query.toLowerCase()))
  const open = accounts.find((a) => a.id === openId) ?? null
  const selectedCount = Object.keys(selected).length
  const monthly = accounts.reduce((sum, a) => sum + monthlyOf(a), 0)
  const unusedMonthly = accounts.filter((a) => a.unused).reduce((sum, a) => sum + monthlyOf(a), 0)
  // 메일로 확인한 상태와 제안할 행동이 있는 계정 (구독·보안·휴면)
  const insightRows = accounts.flatMap((a) => (a.insights ?? []).map((i) => ({ account: a, insight: i })))

  const allChecked = rows.length > 0 && rows.every((a) => selected[a.id])
  const toggleAll = () => rows.forEach((a) => (allChecked ? unselect(a.id) : select(a.id, defaultAction(a))))
  const recommended = accounts.filter((a) => a.recommended && !selected[a.id])
  const addRecommended = () => recommended.forEach((a) => select(a.id, a.recommended!))

  return (
    <div className={open ? 'with-panel' : ''}>
      <div className="page">
        <header className="row between">
          <div>
            <h1>계정 현황 보고서</h1>
            <div className="muted small">
              {new Date().toISOString().slice(0, 10)} 기준 · 메일{' '}
              {scannedMails.toLocaleString()}통 분석{multiMail && ` · 메일 ${mailboxes.length}개`}
              {!live && ' · 목업 데이터'}
            </div>
          </div>
          <button className="primary" disabled={recommended.length === 0} onClick={addRecommended}>
            추천 조치 {recommended.length}개 모두 담기
          </button>
        </header>

        <div className="stats">
          <Stat label="보유 계정" value={`${accounts.length}개`} onClick={() => setFilter('전체')} />
          <Stat label="구독 중" value={`${accounts.filter(isPaying).length}개`} sub={`확인된 금액 월 ${won(monthly)}`} onClick={() => setFilter('구독')} />
          <Stat label="장기 미사용" value={`${accounts.filter(FILTERS.미사용).length}개`} sub={`낭비 추정 월 ${won(unusedMonthly)}`} onClick={() => setFilter('미사용')} />
          <Stat label="보안 알림" value={`${accounts.filter(FILTERS.보안).length}건`} onClick={() => setFilter('보안')} />
          <Stat label="연결 권한" value={`${accounts.filter(FILTERS['연결 권한']).length}개`} onClick={() => setFilter('연결 권한')} />
        </div>

        {insightRows.length > 0 && (
          <section className="stack">
            <div className="section-title">확인이 필요한 계정 {insightRows.length}건</div>
            {INSIGHT_KINDS.map((kind) => {
              const rows = insightRows.filter((r) => r.insight.kind === kind)
              if (rows.length === 0) return null
              const isOpen = openKinds.includes(kind)
              return (
                <div key={kind} className="fold">
                  <button
                    className="fold-head"
                    onClick={() => setOpenKinds((k) => (isOpen ? k.filter((x) => x !== kind) : [...k, kind]))}
                  >
                    <span>
                      {kind} <span className="muted">{rows.length}건</span>
                    </span>
                    <span className="muted small">
                      {isOpen ? '접기' : rows.map((r) => r.account.service).slice(0, 4).join(', ') + (rows.length > 4 ? ' 외' : '')}
                    </span>
                  </button>
                  {isOpen && (
                    <table>
                      <colgroup>
                        <col style={{ width: 180 }} />
                        <col />
                        <col style={{ width: 320 }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <th>계정</th>
                          <th>메일로 확인한 상태</th>
                          <th>IDly가 제안할 행동</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(({ account: a, insight: i }) => (
                          <tr key={`${a.id}-${i.kind}`} className="wrap" onClick={() => setOpenId(a.id)}>
                            <td>{a.service}</td>
                            <td>{i.status}</td>
                            <td>{i.advice}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )
            })}
          </section>
        )}

        <div className="row between">
          <div className="tabs">
            {(Object.keys(FILTERS) as Filter[]).map((f) => (
              <button key={f} className={f === filter ? 'tab active' : 'tab'} onClick={() => setFilter(f)}>
                {f} <span className="muted">{accounts.filter(FILTERS[f]).length}</span>
              </button>
            ))}
          </div>
          <input placeholder="서비스 검색" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>

        <table>
          <colgroup>
            <col style={{ width: 44 }} />
            <col />
            <col style={{ width: 90 }} />
            <col style={{ width: 220 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 110 }} />
          </colgroup>
          <thead>
            <tr>
              <th className="check">
                <input type="checkbox" checked={allChecked} onChange={toggleAll} />
              </th>
              <th>서비스</th>
              <th>분류</th>
              <th>상태</th>
              <th>최근 로그인</th>
              <th className="right">월 결제</th>
              <th>추천 조치</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} className={a.id === openId ? 'active' : ''} onClick={() => setOpenId(a.id)}>
                <td className="check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={!!selected[a.id]}
                    onChange={(e) => (e.target.checked ? select(a.id, defaultAction(a)) : unselect(a.id))}
                  />
                </td>
                <td>
                  {a.service}{' '}
                  <span className="muted small">
                    · {multiMail ? `${a.email} · ` : ''}근거 메일 {a.signals.length}통
                  </span>
                </td>
                <td className="muted">{a.category}</td>
                <td>
                  <Tags account={a} />
                </td>
                <td className="muted">{a.lastLogin ?? '기록 없음'}</td>
                <td className="right">
                  {!isPaying(a) ? '—' : a.subscription!.monthly != null ? won(a.subscription!.monthly) : <span className="muted small">금액 모름</span>}
                </td>
                <td>{a.recommended ?? <span className="muted">—</span>}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  조건에 맞는 계정이 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {dismissed.length > 0 && (
          <div className="row gap small muted">
            <span>잘못 찾은 계정 {dismissed.length}개를 숨겼어요.</span>
            <button className="link" onClick={restoreDismissed}>
              되돌리기
            </button>
          </div>
        )}

        {selectedCount > 0 && (
          <div className="action-bar">
            <span>{selectedCount}개 계정 선택됨</span>
            <div className="row gap">
              <button className="link" onClick={() => Object.keys(selected).forEach(unselect)}>
                선택 해제
              </button>
              <button className="primary" onClick={() => navigate('/cleanup')}>
                정리하기
              </button>
            </div>
          </div>
        )}
      </div>

      {open && <DetailPanel account={open} onClose={() => setOpenId(null)} />}
    </div>
  )
}

function Stat({ label, value, sub, onClick }: { label: string; value: string; sub?: string; onClick: () => void }) {
  return (
    <button className="stat" onClick={onClick}>
      <div className="muted small">{label}</div>
      <div className="num">{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </button>
  )
}

export function Tags({ account: a }: { account: Account }) {
  return (
    <span className="tags">
      {a.subscription && (
        <span className="tag">
          {(a.subscription.status ?? '활성') === '활성' ? '구독' : `구독 ${a.subscription.status}`}
        </span>
      )}
      {a.unused && <span className="tag">미사용</span>}
      {a.securityAlert && <span className="tag strong">보안</span>}
      {a.permissions.length > 0 && <span className="tag">권한 {a.permissions.length}</span>}
    </span>
  )
}

function DetailPanel({ account: a, onClose }: { account: Account; onClose: () => void }) {
  const { selected, select, unselect, dismiss } = useStore()
  const chosen = selected[a.id]

  return (
    <aside className="panel">
      <div className="row between">
        <h2>{a.service}</h2>
        <button className="link" onClick={onClose}>
          닫기
        </button>
      </div>
      <Tags account={a} />

      <dl>
        <dt>계정 메일</dt>
        <dd>{a.email}</dd>
        <dt>가입일</dt>
        <dd>{a.signupDate}</dd>
        <dt>최근 로그인</dt>
        <dd>{a.lastLogin ?? '기록 없음'}</dd>
        {a.subscription && (
          <>
            <dt>구독</dt>
            <dd>
              {a.subscription.plan} · {a.subscription.status ?? '활성'}
              {a.subscription.monthly != null && ` · 월 ${won(a.subscription.monthly)}`}
              {a.subscription.nextBilling && <div className="muted small">다음 결제 {a.subscription.nextBilling}</div>}
            </dd>
          </>
        )}
      </dl>

      {(a.insights ?? []).map((i) => (
        <div key={i.kind} className="notice">
          <strong>{i.kind}</strong>
          <div>{i.status}</div>
          <div className="small">→ {i.advice}</div>
        </div>
      ))}

      {a.securityAlert && !a.insights?.some((i) => i.kind === '보안') && (
        <div className="notice">
          <strong>보안 알림</strong>
          <div>{a.securityAlert}</div>
        </div>
      )}

      {a.permissions.length > 0 && (
        <div>
          <div className="section-title">Google 계정 연결 권한</div>
          <ul className="plain">
            {a.permissions.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <div className="section-title">근거 메일</div>
        <ul className="timeline">
          {a.signals.map((s) => (
            <li key={s.date + s.subject}>
              <span className="muted small">{s.date}</span>
              <span className="tag">{s.type}</span>
              <span>{s.subject}</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <div className="section-title">정리 방식</div>
        <p className="muted small">
          {a.automatable
            ? 'IDly가 대신 처리합니다. 로그인·본인인증이 필요하면 그 단계만 직접 입력해요. (이용권 1회)'
            : '자동 대행을 아직 지원하지 않아 처리 순서를 안내합니다. (무료)'}
        </p>
        <div className="row gap wrap">
          {availableActions(a).map((act) => (
            <button
              key={act}
              className={chosen === act ? 'primary' : ''}
              onClick={() => (chosen === act ? unselect(a.id) : select(a.id, act))}
            >
              {act}
              {a.recommended === act && ' (추천)'}
            </button>
          ))}
        </div>
        {chosen && <p className="muted small">정리 목록에 담겼습니다. 다시 누르면 빠집니다.</p>}
      </div>

      <button
        className="link"
        onClick={() => {
          dismiss(a.id)
          onClose()
        }}
      >
        내 계정이 아니에요 / 잘못 찾았어요
      </button>
    </aside>
  )
}
