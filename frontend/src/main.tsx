import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './wireframe.css'
import { StoreProvider, useStore } from './store'
import Layout from './Layout'
import Auth from './pages/Auth'
import Connect from './pages/Connect'
import Scan from './pages/Scan'
import Report from './pages/Report'
import Cleanup from './pages/Cleanup'
import Progress from './pages/Progress'
import Credits from './pages/Credits'

// IDly에 로그인해야 들어갈 수 있는 화면 (목업 둘러보기 포함)
function RequireUser({ children }: { children: ReactNode }) {
  const { user, restoring } = useStore()
  // 서버 세션을 되살리는 동안에는 로그인 화면으로 튕기지 않는다
  if (restoring) return null
  return user ? children : <Navigate to="/" replace />
}

// 로그인돼 있으면 첫 화면 대신 보고서(메일이 없으면 메일 연동)로
function Start() {
  const { user, mailboxes, restoring } = useStore()
  if (restoring) return null
  if (!user) return <Auth />
  return <Navigate to={mailboxes.length > 0 ? '/report' : '/add-mail'} replace />
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Start />} />
      <Route path="/add-mail" element={<RequireUser><Connect /></RequireUser>} />
      <Route path="/scan" element={<RequireUser><Scan /></RequireUser>} />
      <Route element={<RequireUser><Layout /></RequireUser>}>
        <Route path="/report" element={<Report />} />
        <Route path="/cleanup" element={<Cleanup />} />
        <Route path="/progress" element={<Progress />} />
        <Route path="/credits" element={<Credits />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <StoreProvider>
        <App />
      </StoreProvider>
    </BrowserRouter>
  </StrictMode>,
)
