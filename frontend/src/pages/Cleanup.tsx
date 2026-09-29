import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { availableActions, monthlyOf, useStore, won } from '../store'
import type { Account, Action } from '../mock'

const ACTION_NOTE: Record<Action, string> = {
  탈퇴: '계정과 데이터가 삭제되며 되돌릴 수 없습니다.',
  '구독 해지': '다음 결제일부터 청구되지 않습니다.',
  '권한 해제': '해당 서비스의 Google 계정 접근을 끊습니다.',
}

export default function Cleanup() {
  const { accounts, selected, credits, startCleanup, extension, live } = useStore()
  const navigate = useNavigate()
  const [agreed, setAgreed] = useState(false)

  const items = accounts.filter((a) => selected[a.id])
  const auto = items.filter((a) => a.automatable)
  const manual = items.filter((a) => !a.automatable)
  const shortage = auto.length - credits
  const hasWithdraw = items.some((a) => selected[a.id] === '탈퇴')
  const saved = items
    .filter((a) => selected[a.id] !== '권한 해제')
    .reduce((sum, a) => sum + monthlyOf(a), 0)

  if (items.length === 0) {
    return (
      <div className="page">
        <h1>정리하기</h1>
        <div className="empty-box">
          <p>선택한 계정이 없습니다.</p>
          <button onClick={() => navigate('/report')}>계정 현황에서 선택하기</button>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <header>
        <h1>정리 전 확인</h1>
        <div className="muted small">계정마다 정리 방식을 확인하세요.</div>
      </header>

      {auto.length > 0 && (
        <section className="stack">
          <div>
            <div className="section-title">IDly가 대신 처리 · {auto.length}개</div>
            <div className="muted small">
              {extension
                ? '내 크롬의 새 탭에서 IDly 확장이 탈퇴·해지 메뉴를 찾아 진행해요. 이미 로그인된 사이트는 로그인 없이 진행되고, 로그인이 필요하면 그 탭에서 직접 하시면 돼요. 비밀번호는 IDly로 전달되지 않아요.'
                : 'IDly 서버의 브라우저에서 에이전트가 진행하고, 로그인·본인인증은 원격 화면으로 직접 입력해요.'}{' '}
              되돌릴 수 없는 버튼은 누르기 전에 꼭 확인을 받고, 찾지 못하면 직접 처리 안내로 바꾸고 이용권을 돌려드려요.
            </div>
          </div>
          {!extension && live && (
            <div className="notice small">
              <strong>IDly 크롬 확장을 설치하면 더 편해요</strong>
              <span>
                이미 로그인된 내 브라우저에서 진행돼 다시 로그인하지 않아도 되고, 본인인증 팝업도 평소처럼 떠요.
              </span>
              <ol className="steps">
                <li>크롬 주소창에 chrome://extensions 입력 → 오른쪽 위 개발자 모드 켜기</li>
                <li>
                  "압축해제된 확장 프로그램 로드" → 프로젝트의 <code>extension</code> 폴더 선택
                </li>
                <li>이 페이지를 새로고침</li>
              </ol>
            </div>
          )}
          <ItemTable items={auto} />
        </section>
      )}

      {manual.length > 0 && (
        <section className="stack">
          <div>
            <div className="section-title">직접 처리 안내 · {manual.length}개</div>
            <div className="muted small">자동 대행을 아직 지원하지 않는 사이트입니다. 처리 순서를 안내해 드리며 이용권을 쓰지 않아요.</div>
          </div>
          <ItemTable items={manual} />
        </section>
      )}

      <div className="summary">
        <div className="row between">
          <span>절약되는 월 구독료</span>
          <span>{won(saved)}</span>
        </div>
        <div className="row between">
          <span>사용할 이용권</span>
          <span>
            {auto.length}회 / 보유 {credits}회
          </span>
        </div>
        <div className="muted small">IDly가 끝내 처리하지 못해 직접 처리로 바꾸면 이용권을 돌려드려요.</div>
      </div>

      {shortage > 0 ? (
        <div className="notice">
          <div>이용권이 {shortage}회 부족합니다. 이용권을 구매하거나 선택을 줄여주세요.</div>
          <div className="row gap">
            <button className="primary" onClick={() => navigate('/credits')}>
              이용권 구매
            </button>
            <button onClick={() => navigate('/report')}>선택 수정</button>
          </div>
        </div>
      ) : (
        <div className="stack">
          {hasWithdraw && (
            <label className="row gap">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
              탈퇴는 되돌릴 수 없다는 점을 확인했습니다. 탈퇴 직전 단계에서 한 번 더 확인을 요청합니다.
            </label>
          )}
          <div className="row gap">
            <button
              className="primary lg"
              disabled={hasWithdraw && !agreed}
              onClick={() => {
                startCleanup()
                navigate('/progress')
              }}
            >
              {items.length}개 계정 정리 시작
            </button>
            <button className="lg" onClick={() => navigate('/report')}>
              돌아가기
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ItemTable({ items }: { items: Account[] }) {
  const { selected, select, unselect } = useStore()
  return (
    <table>
      <colgroup>
        <col style={{ width: 180 }} />
        <col style={{ width: 160 }} />
        <col />
        <col style={{ width: 80 }} />
      </colgroup>
      <thead>
        <tr>
          <th>서비스</th>
          <th>정리 방식</th>
          <th>영향</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {items.map((a) => (
          <tr key={a.id}>
            <td>{a.service}</td>
            <td>
              <select value={selected[a.id]} onChange={(e) => select(a.id, e.target.value as Action)}>
                {availableActions(a).map((act) => (
                  <option key={act}>{act}</option>
                ))}
              </select>
            </td>
            <td className="muted small">{ACTION_NOTE[selected[a.id]]}</td>
            <td className="right">
              <button className="link" onClick={() => unselect(a.id)}>
                빼기
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
