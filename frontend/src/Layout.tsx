import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useStore } from './store'

export default function Layout() {
  const { user, live, mailboxes, scanFor, removeMailbox, logout, selected, jobs, credits } = useStore()
  const navigate = useNavigate()
  const selectedCount = Object.keys(selected).length
  // 사용자가 손대야 하는 작업 수
  const needsUser = jobs.filter((j) => j.status === '입력 필요' || j.status === '확인 필요' || j.status === '직접 처리').length

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">IDly</div>
        <nav>
          <NavLink to="/report">계정 현황</NavLink>
          <NavLink to="/cleanup">
            정리하기 {selectedCount > 0 && <span className="count">{selectedCount}</span>}
          </NavLink>
          <NavLink to="/progress">
            정리 내역 {needsUser > 0 && <span className="count">{needsUser}</span>}
          </NavLink>
          <NavLink to="/credits">
            이용권 <span className="muted">{credits}회</span>
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          <div className="muted small">연동된 메일 {mailboxes.length}개</div>
          <ul className="mail-list">
            {mailboxes.map((m) => {
              const scan = scanFor(m.email)
              return (
                <li key={m.email}>
                  <NavLink to={`/scan?mail=${encodeURIComponent(m.email)}`} className="mail-name" title={m.email}>
                    {m.email}
                  </NavLink>
                  <span className="small muted">
                    {scan.error ? '실패' : !scan.done ? `${Math.round(scan.ratio * 100)}%` : ''}
                  </span>
                  {live && (
                    <button className="link small" onClick={() => removeMailbox(m.email)}>
                      빼기
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
          {live && (
            <button className="link" onClick={() => navigate('/add-mail')}>
              + 메일 추가
            </button>
          )}
          <div className="account">
            <div className="muted small">IDly 계정</div>
            <div className="mail-name" title={user?.email}>
              {live ? user?.email : '둘러보기 (로그인 안 함)'}
            </div>
            <button
              className="link"
              onClick={() => {
                logout()
                navigate('/')
              }}
            >
              {live ? '로그아웃' : '둘러보기 끝내기'}
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
