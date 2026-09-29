import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore, won } from '../store'
import { PACK } from '../mock'

export default function Credits() {
  const { credits, purchases, buyPack, selected } = useStore()
  const navigate = useNavigate()
  const [checkout, setCheckout] = useState(false)
  const selectedCount = Object.keys(selected).length

  return (
    <div className="page">
      <header>
        <h1>이용권</h1>
        <div className="muted small">
          계정 현황 보고서는 무료입니다. IDly가 대신 처리한 계정만 1회씩 쓰고, 직접 처리 안내는 무료이며, 대행을 포기하면 돌려드려요.
        </div>
      </header>

      <div className="stats">
        <div className="stat">
          <div className="muted small">남은 정리 횟수</div>
          <div className="num">{credits}회</div>
        </div>
        <div className="stat">
          <div className="muted small">정리 대기 중인 선택</div>
          <div className="num">{selectedCount}개</div>
        </div>
      </div>

      <div className="product">
        <div>
          <div className="section-title">계정 정리 {PACK.count}회</div>
          <div className="num">{won(PACK.price)}</div>
          <div className="muted small">회당 {won(Math.round(PACK.price / PACK.count))} · 유효기간 없음</div>
        </div>
        {!checkout ? (
          <button className="primary" onClick={() => setCheckout(true)}>
            구매하기
          </button>
        ) : (
          <div className="stack">
            <div className="ph" style={{ height: 120 }}>결제 수단 선택 (PG 연동 영역)</div>
            <div className="row gap">
              <button
                className="primary"
                onClick={() => {
                  buyPack()
                  setCheckout(false)
                }}
              >
                {won(PACK.price)} 결제
              </button>
              <button onClick={() => setCheckout(false)}>취소</button>
            </div>
          </div>
        )}
      </div>

      {selectedCount > 0 && credits >= selectedCount && (
        <button onClick={() => navigate('/cleanup')}>선택한 {selectedCount}개 계정 정리하러 가기</button>
      )}

      <div>
        <div className="section-title">구매 내역</div>
        <table>
          <thead>
            <tr>
              <th>날짜</th>
              <th>내용</th>
              <th className="right">금액</th>
            </tr>
          </thead>
          <tbody>
            {purchases.map((p, i) => (
              <tr key={i}>
                <td>{p.date}</td>
                <td>계정 정리 {p.count}회</td>
                <td className="right">{won(p.price)}</td>
              </tr>
            ))}
            <tr>
              <td className="muted">가입 시</td>
              <td>무료 제공 — 계정 현황 보고서 + 계정 정리 1회</td>
              <td className="right">0원</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="muted small">정기 관리 이용권(신규 가입·결제·장기 미사용 알림)은 준비 중입니다.</div>
    </div>
  )
}
