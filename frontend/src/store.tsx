import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { accounts as mockAccounts, CONNECTED_EMAIL, PACK, type Account, type Action } from './mock'
import {
  api,
  extensionBridge,
  type ActionInput,
  type ActionRun,
  type DiscoveryReport,
  type ExtensionLaunch,
  type Session,
  type SyncJob,
} from './api'

// 정리는 클라우드 브라우저에서 에이전트가 대행한다.
// 로그인·본인인증이 필요하면 '입력 필요'로 멈추고 사용자가 원격 화면에서 직접 입력한다.
export type JobStatus = '대기' | '진행 중' | '입력 필요' | '확인 필요' | '직접 처리' | '완료'

export interface Job {
  id: string
  accountId: string
  action: Action
  status: JobStatus
  // 이용권을 쓴 작업인지 (자동 정리만 차감, 실패하면 돌려준다)
  charged: boolean
  // 사용자가 원격 화면에서 인증을 마쳤는지 (목업 시뮬레이션용)
  inputDone?: boolean
  // 실제 에이전트 작업 ID (live). 없으면 목업 시뮬레이션
  runId?: string
  // extension: 사용자 크롬의 IDly 확장, 그 외: 서버 클라우드 브라우저
  mode?: ActionRun['mode']
  note?: string
}

// 목업에서 쓰는 계정 id는 도메인이 아니라서, live 계정 id(`메일:도메인`)에서 도메인만 꺼낸다
const domainOf = (accountId: string) => accountId.slice(accountId.indexOf(':') + 1)

export interface Purchase {
  date: string
  count: number
  price: number
}

// 목업 탐색 진행 (live가 아닐 때)
const MOCK_SCAN_STEPS = 20

// 연동한 메일 하나와 그 메일의 탐색 상태
export interface MailboxState {
  email: string
  job: SyncJob | null
  report: DiscoveryReport | null
  error: string | null
}

export interface ScanState {
  ratio: number
  done: boolean
  error: string | null
  job: SyncJob | null
  report: DiscoveryReport | null
}

interface Store {
  // 로그인한 IDly 계정. 연동한 메일함은 모두 이 계정에 속한다 (목업이면 가짜 계정)
  user: { email: string } | null
  // true면 실제 메일 연동, false면 목업 둘러보기
  live: boolean
  // 새로고침 뒤 서버 세션을 되살리는 중
  restoring: boolean
  mailboxes: MailboxState[]
  applySession: (session: Session) => void
  startMock: () => void
  removeMailbox: (email: string) => void
  logout: () => void

  scanFor: (email: string) => ScanState
  // force면 이미 결과가 있어도 다시 탐색
  startScan: (email: string, force?: boolean) => void

  accounts: Account[]
  dismissed: string[]
  dismiss: (id: string) => void
  restoreDismissed: () => void

  selected: Record<string, Action>
  select: (id: string, action: Action) => void
  unselect: (id: string) => void
  clearSelection: () => void

  credits: number
  purchases: Purchase[]
  buyPack: () => void

  jobs: Job[]
  startCleanup: () => void
  // 원격 화면 입력 (클릭·글자·키)을 에이전트 브라우저로 보낸다
  sendInput: (jobId: string, input: ActionInput) => void
  // IDly 크롬 확장이 설치돼 있는지 (있으면 정리를 사용자 크롬에서 진행)
  extension: boolean
  focusJobTab: (jobId: string) => void
  confirmJob: (jobId: string) => void
  markManualDone: (jobId: string) => void
  resolveInput: (jobId: string) => void
  cancelJob: (jobId: string) => void
  switchToManual: (jobId: string) => void
}

const StoreContext = createContext<Store | null>(null)

// 첫 계정 정리 1회 무료
const FREE_CREDITS = 1

export function StoreProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<{ email: string } | null>(null)
  const [live, setLive] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const [mailboxes, setMailboxes] = useState<MailboxState[]>([])
  const [mockStep, setMockStep] = useState<number | null>(null)
  const [dismissed, setDismissed] = useState<string[]>([])
  const [selected, setSelected] = useState<Record<string, Action>>({})
  const [credits, setCredits] = useState(FREE_CREDITS)
  const [purchases, setPurchases] = useState<Purchase[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  // StrictMode에서 두 번 불려도 메일마다 탐색은 한 번만 시작
  const scanRequested = useRef(new Set<string>())
  const [extension, setExtension] = useState(extensionBridge.installed())

  // IDly 확장이 페이지에 알려오면 켠다 (extension/bridge.js)
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source === window && e.data?.source === 'idly-ext' && e.data.type === 'READY') setExtension(true)
    }
    window.addEventListener('message', onMessage)
    extensionBridge.ping()
    return () => window.removeEventListener('message', onMessage)
  }, [])

  const patchMailbox = (email: string, patch: Partial<MailboxState>) =>
    setMailboxes((prev) => prev.map((m) => (m.email === email ? { ...m, ...patch } : m)))

  const applySession = (session: Session) => {
    if (!session.user) {
      reset()
      return
    }
    setLive(true)
    setUser(session.user)
    setMailboxes((prev) =>
      session.mailboxes.map(
        (m) => prev.find((p) => p.email === m.email) ?? { email: m.email, job: null, report: null, error: null },
      ),
    )
    // 화면에 없는 메일함은 서버의 진행 중 작업이나 저장된 결과를 붙인다
    session.mailboxes.forEach((m) => {
      if (mailboxes.some((p) => p.email === m.email && (p.job || p.report))) return
      // 새로 연동한 메일(결과도 작업도 없음)은 탐색 화면에서 탐색을 시작하도록 남겨 둔다
      if (!m.job_id && !m.scanned_at) return
      scanRequested.current.add(m.email)
      const loadSaved = () => {
        if (m.scanned_at) api.mailboxReport(m.email).then((report) => patchMailbox(m.email, { report })).catch(() => {})
      }
      if (!m.job_id) return loadSaved()
      api
        .syncStatus(m.job_id)
        .then((job) => (job.status === '받는 중' || job.status === '분석 중' ? patchMailbox(m.email, { job }) : loadSaved()))
        .catch(loadSaved)
    })
  }

  // 새로고침 뒤 서버 세션 복원
  useEffect(() => {
    api
      .me()
      .then(applySession)
      .catch(() => {})
      .finally(() => setRestoring(false))
  }, [])

  // 목업 탐색 진행
  useEffect(() => {
    if (mockStep === null || mockStep >= MOCK_SCAN_STEPS) return
    const timer = setTimeout(() => setMockStep((s) => (s ?? 0) + 1), 150)
    return () => clearTimeout(timer)
  }, [mockStep])

  // 메일마다 받기·분석 진행을 폴링하고, 끝나면 탐색 결과를 가져온다
  useEffect(() => {
    const pending = mailboxes.filter((m) => m.job && m.job.status !== '실패' && !m.report && !m.error)
    if (pending.length === 0) return
    const timer = setTimeout(() => {
      pending.forEach(({ email, job }) => {
        const fail = (e: Error) => patchMailbox(email, { error: e.message })
        if (job!.status === '완료') api.syncReport(job!.id).then((report) => patchMailbox(email, { report })).catch(fail)
        else api.syncStatus(job!.id).then((next) => patchMailbox(email, { job: next })).catch(fail)
      })
    }, 1000)
    return () => clearTimeout(timer)
  }, [mailboxes])

  // live면 모든 메일에서 찾은 계정을 합치고, 아니면 목업.
  // 같은 서비스라도 메일이 다르면 다른 계정이므로 id에 메일을 붙인다
  const allAccounts: Account[] = live
    ? mailboxes.flatMap((m) => (m.report?.accounts ?? []).map((a) => ({ ...a, id: `${m.email}:${a.id}` })))
    : mockAccounts

  const liveRatio = (m: MailboxState) => {
    if (m.report) return 1
    const job = m.job
    if (!job) return 0
    // 메일 받기 0~80%, 분석 80~100%
    if (job.status === '분석 중' || job.status === '완료') {
      return { '헤더 분석': 0.8, '결제 메일 확인': 0.85, 'AI 판별': 0.9 }[job.step ?? ''] ?? 0.8
    }
    return job.total > 0 ? (job.fetched / job.total) * 0.8 : 0
  }

  const reset = () => {
    setUser(null)
    setLive(false)
    setMailboxes([])
    setMockStep(null)
    setDismissed([])
    setSelected({})
    setJobs([])
    scanRequested.current.clear()
  }

  // 실제 에이전트 작업 상태를 따라간다. 에이전트가 실패하면 직접 처리로 바꾸고 이용권을 돌려준다
  const refundNote = '이용권 1회를 돌려드렸어요'
  const applyRun = (job: Job, run: ActionRun) => {
    if (run.status === '취소됨') return
    if (run.status === '실패') {
      if (job.charged) setCredits((c) => c + 1)
      // 어디서 돌다 실패했는지도 보여준다 (확장이 안 잡혀 클라우드로 간 경우를 알 수 있게)
      const where = run.mode === 'extension' ? '내 크롬' : run.mode ? '클라우드 브라우저' : null
      const reason = run.error ?? run.message
      setJobs((prev) =>
        prev.map((j) =>
          j.id === job.id
            ? {
                ...j,
                status: '직접 처리',
                charged: false,
                note: `에이전트가 진행하지 못했어요${where ? ` (${where})` : ''}: ${reason} · ${refundNote}`,
              }
            : j,
        ),
      )
      return
    }
    setJobs((prev) => prev.map((j) => (j.id === job.id ? { ...j, status: run.status as JobStatus, note: run.message } : j)))
  }

  useEffect(() => {
    const active = jobs.filter((j) => j.runId && j.status !== '완료' && j.status !== '직접 처리')
    if (active.length === 0) return
    const timer = setTimeout(() => {
      active.forEach((job) => api.actionStatus(job.runId!).then((run) => applyRun(job, run)).catch(() => {}))
    }, 1000)
    return () => clearTimeout(timer)
  }, [jobs])

  // 목업 정리 자동화 시뮬레이션 (runId 없는 작업만): 한 번에 한 작업씩 상태를 넘긴다
  useEffect(() => {
    if (live) return
    const running = jobs.find((j) => j.status === '진행 중')
    const queued = jobs.find((j) => j.status === '대기')
    if (!running && !queued) return
    const timer = setTimeout(() => {
      if (running) {
        const account = allAccounts.find((a) => a.id === running.accountId)
        let next: Job
        if (account?.blocker && !running.inputDone) {
          next = { ...running, status: '입력 필요', note: account.blocker }
        } else if (running.action === '탈퇴') {
          next = { ...running, status: '확인 필요', note: '탈퇴 직전입니다. 확정하면 되돌릴 수 없어요' }
        } else {
          next = { ...running, status: '완료', note: undefined }
        }
        setJobs((prev) => prev.map((j) => (j.id === running.id ? next : j)))
      } else if (queued) {
        setJobs((prev) => prev.map((j) => (j.id === queued.id ? { ...j, status: '진행 중' } : j)))
      }
    }, 1200)
    return () => clearTimeout(timer)
  }, [jobs])

  const store: Store = {
    user,
    live,
    restoring,
    mailboxes,
    applySession,
    startMock: () => {
      reset()
      setUser({ email: CONNECTED_EMAIL })
      setMailboxes([{ email: CONNECTED_EMAIL, job: null, report: null, error: null }])
    },
    removeMailbox: (email) => {
      if (live) api.removeMailbox(email).catch(() => {})
      setMailboxes((prev) => prev.filter((m) => m.email !== email))
      setSelected((s) => Object.fromEntries(Object.entries(s).filter(([id]) => !id.startsWith(`${email}:`))))
      scanRequested.current.delete(email)
    },
    logout: () => {
      if (live) api.logout().catch(() => {})
      reset()
    },

    scanFor: (email) => {
      if (!live) {
        return { ratio: (mockStep ?? 0) / MOCK_SCAN_STEPS, done: mockStep === MOCK_SCAN_STEPS, error: null, job: null, report: null }
      }
      const m = mailboxes.find((x) => x.email === email)
      if (!m) return { ratio: 0, done: false, error: null, job: null, report: null }
      return { ratio: liveRatio(m), done: !!m.report, error: m.error ?? m.job?.error ?? null, job: m.job, report: m.report }
    },
    startScan: (email, force = false) => {
      if (scanRequested.current.has(email) && !force) return
      scanRequested.current.add(email)
      if (!live) {
        setMockStep(0)
        return
      }
      patchMailbox(email, { error: null })
      api
        .startSync(email)
        .then((job) => patchMailbox(email, { job, report: null }))
        .catch((e) => {
          patchMailbox(email, { error: e.message })
          scanRequested.current.delete(email)
        })
    },

    accounts: allAccounts.filter((a) => !dismissed.includes(a.id)),
    dismissed,
    dismiss: (id) => {
      setDismissed((d) => [...d, id])
      setSelected(({ [id]: _, ...rest }) => rest)
    },
    restoreDismissed: () => setDismissed([]),

    selected,
    select: (id, action) => setSelected((s) => ({ ...s, [id]: action })),
    unselect: (id) => setSelected(({ [id]: _, ...rest }) => rest),
    clearSelection: () => setSelected({}),

    credits,
    purchases,
    buyPack: () => {
      setCredits((c) => c + PACK.count)
      setPurchases((p) => [{ date: new Date().toISOString().slice(0, 10), ...PACK }, ...p])
    },

    jobs,
    startCleanup: () => {
      const entries = Object.entries(selected)
      const now = Date.now()
      const newJobs: Job[] = entries.map(([accountId, action]) => {
        const auto = allAccounts.find((a) => a.id === accountId)?.automatable ?? false
        return {
          id: `${accountId}-${now}`,
          accountId,
          action,
          status: auto ? '대기' : '직접 처리',
          charged: auto,
        }
      })
      setCredits((c) => c - newJobs.filter((j) => j.charged).length)
      setJobs((prev) => [...newJobs, ...prev])
      setSelected({})
      if (!live) return
      // live: 에이전트 작업을 서버에 만든다. 확장이 있으면 사용자 크롬에서, 없으면 클라우드 브라우저에서.
      // 지원하지 않는 곳이면 직접 처리로 돌리고 환불
      const runner = extension ? 'extension' : 'cloud'
      newJobs
        .filter((j) => j.charged)
        .forEach((job) => {
          const account = allAccounts.find((a) => a.id === job.accountId)!
          api
            .startAction({
              domain: domainOf(job.accountId),
              service: account.service,
              account_email: account.email,
              action: job.action,
              runner,
            })
            .then((run) => {
              if (run.mode === 'extension') extensionBridge.start(run as ActionRun & ExtensionLaunch)
              setJobs((prev) =>
                prev.map((j) => (j.id === job.id ? { ...j, runId: run.id, mode: run.mode, note: run.message } : j)),
              )
            })
            .catch((e) => applyRun(job, { status: '실패', error: e.message, message: '' } as ActionRun))
        })
    },
    extension,
    focusJobTab: (jobId) => {
      const runId = jobs.find((j) => j.id === jobId)?.runId
      if (runId) extensionBridge.focus(runId)
    },
    sendInput: (jobId, input) => {
      const runId = jobs.find((j) => j.id === jobId)?.runId
      if (runId) api.actionInput(runId, input).catch(() => {})
    },
    confirmJob: (jobId) => {
      const runId = jobs.find((j) => j.id === jobId)?.runId
      if (runId) {
        api.actionInput(runId, { type: 'confirm' }).catch(() => {})
        setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: '진행 중', note: '확정했어요. 마무리하는 중' } : j)))
        return
      }
      setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: '완료', note: undefined } : j)))
    },
    markManualDone: (jobId) =>
      setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: '완료', note: '직접 처리함' } : j))),
    // 인증을 마치면 에이전트가 이어서 진행한다
    resolveInput: (jobId) => {
      const runId = jobs.find((j) => j.id === jobId)?.runId
      if (runId) api.actionInput(runId, { type: 'resume' }).catch(() => {})
      setJobs((prev) =>
        prev.map((j) => (j.id === jobId ? { ...j, status: '진행 중', inputDone: true, note: undefined } : j)),
      )
    },
    // 탈퇴 직전에 취소하면 작업을 지우고 이용권을 돌려준다
    cancelJob: (jobId) => {
      const job = jobs.find((j) => j.id === jobId)
      if (job?.runId) api.actionInput(job.runId, { type: 'cancel' }).catch(() => {})
      if (job?.charged) setCredits((c) => c + 1)
      setJobs((prev) => prev.filter((j) => j.id !== jobId))
    },
    // 대행을 포기하고 직접 처리로 돌리면 이용권을 돌려준다
    switchToManual: (jobId) => {
      const job = jobs.find((j) => j.id === jobId)
      if (job?.runId) api.actionInput(job.runId, { type: 'cancel' }).catch(() => {})
      if (job?.charged) setCredits((c) => c + 1)
      setJobs((prev) =>
        prev.map((j) =>
          j.id === jobId ? { ...j, status: '직접 처리', charged: false, note: '이용권 1회를 돌려드렸어요' } : j,
        ),
      )
    },
  }

  return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
}

export function useStore() {
  const store = useContext(StoreContext)
  if (!store) throw new Error('StoreProvider 밖에서 useStore 사용')
  return store
}

// 지금 돈이 나가고 있는 구독인지 (해지됨·체험 종료는 아님)
export function isPaying(account: Account): boolean {
  const status = account.subscription?.status ?? '활성'
  return !!account.subscription && (status === '활성' || status === '만료 예정')
}

// 합계에 넣을 월 결제액 (금액을 모르면 0)
export const monthlyOf = (account: Account) => (isPaying(account) ? account.subscription!.monthly ?? 0 : 0)

export function defaultAction(account: Account): Action {
  if (account.recommended) return account.recommended
  if (isPaying(account)) return '구독 해지'
  if (account.permissions.length > 0) return '권한 해제'
  return '탈퇴'
}

export function availableActions(account: Account): Action[] {
  const actions: Action[] = []
  if (isPaying(account)) actions.push('구독 해지')
  if (account.permissions.length > 0) actions.push('권한 해제')
  actions.push('탈퇴')
  return actions
}

export function manualSteps(account: Account, action: Action): string[] {
  if (account.manualSteps) return account.manualSteps
  if (action === '권한 해제') return ['Google 계정 > 보안 > 서드파티 앱 및 서비스', `${account.service} 선택`, '모든 연결 삭제']
  return [`${account.service} 로그인`, `계정 설정에서 ${action} 메뉴 찾기`, `${action} 진행`]
}

export const won = (n: number) => `${n.toLocaleString('ko-KR')}원`
