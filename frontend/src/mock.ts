// 백엔드 연동 전까지 쓰는 목업 데이터. API가 생기면 이 파일만 교체한다.

export type Action = '탈퇴' | '구독 해지' | '권한 해제'

// 구독: 구독 상태 안내, 안내: 휴면·삭제·약관 등 회원 대상 고지
export type SignalType = '가입' | '인증' | '결제' | '구독' | '로그인' | '보안' | '안내'

export interface Signal {
  date: string
  type: SignalType
  subject: string
}

export type SubscriptionStatus = '활성' | '만료 예정' | '체험 종료' | '해지됨'

export interface Subscription {
  plan: string
  // 메일에서 금액을 못 찾으면 null
  monthly: number | null
  nextBilling: string | null
  // 없으면 '활성' (목업)
  status?: SubscriptionStatus
  lastEventDate?: string | null
  lastEventSubject?: string
}

// 메일로 확인한 상태와 IDly가 제안할 행동
export interface Insight {
  kind: '구독' | '보안' | '휴면'
  date: string
  status: string
  advice: string
}

export interface Account {
  id: string
  service: string
  category: string
  email: string
  signupDate: string
  lastLogin: string | null
  subscription: Subscription | null
  unused: boolean
  securityAlert: string | null
  insights?: Insight[]
  permissions: string[]
  automatable: boolean
  // 자동 정리 도중 막히는 이유 (목업에서 실패 흐름을 보여주기 위함)
  blocker?: string
  // 자동화를 지원하지 않는 사이트의 직접 처리 순서
  manualSteps?: string[]
  recommended: Action | null
  signals: Signal[]
}

export const CONNECTED_EMAIL = 'user@gmail.com'
export const TOTAL_MAILS = 12480

export const accounts: Account[] = [
  {
    id: 'netflix',
    service: '넷플릭스',
    category: 'OTT',
    email: CONNECTED_EMAIL,
    signupDate: '2021-03-02',
    lastLogin: '2026-09-20',
    subscription: { plan: '스탠다드', monthly: 13500, nextBilling: '2026-10-02' },
    unused: false,
    securityAlert: null,
    permissions: [],
    automatable: true,
    recommended: null,
    signals: [
      { date: '2026-09-02', type: '결제', subject: '넷플릭스 결제 영수증' },
      { date: '2026-09-20', type: '로그인', subject: '새 기기에서 로그인' },
      { date: '2021-03-02', type: '가입', subject: '넷플릭스에 오신 것을 환영합니다' },
    ],
  },
  {
    id: 'watcha',
    service: '왓챠',
    category: 'OTT',
    email: CONNECTED_EMAIL,
    signupDate: '2022-07-11',
    lastLogin: '2025-11-03',
    subscription: { plan: '베이직', monthly: 7900, nextBilling: '2026-10-11' },
    unused: true,
    securityAlert: null,
    permissions: [],
    automatable: true,
    recommended: '구독 해지',
    signals: [
      { date: '2026-09-11', type: '결제', subject: '왓챠 정기결제 완료 안내' },
      { date: '2025-11-03', type: '로그인', subject: '로그인 알림' },
      { date: '2022-07-11', type: '가입', subject: '왓챠 가입을 환영합니다' },
    ],
  },
  {
    id: 'melon',
    service: '멜론',
    category: '음악',
    email: CONNECTED_EMAIL,
    signupDate: '2019-02-14',
    lastLogin: '2026-09-25',
    subscription: { plan: '스트리밍 클럽', monthly: 10900, nextBilling: '2026-10-14' },
    unused: false,
    securityAlert: null,
    permissions: [],
    automatable: true,
    recommended: null,
    signals: [
      { date: '2026-09-14', type: '결제', subject: '멜론 이용권 결제 안내' },
      { date: '2019-02-14', type: '가입', subject: '멜론 회원가입 완료' },
    ],
  },
  {
    id: 'canva',
    service: 'Canva',
    category: '디자인',
    email: CONNECTED_EMAIL,
    signupDate: '2024-03-20',
    lastLogin: '2025-06-18',
    subscription: { plan: 'Pro', monthly: 14900, nextBilling: '2026-10-20' },
    unused: true,
    securityAlert: null,
    permissions: ['Google 계정 기본 정보', 'Google Drive 파일 읽기'],
    automatable: true,
    recommended: '구독 해지',
    signals: [
      { date: '2026-09-20', type: '결제', subject: 'Your Canva Pro receipt' },
      { date: '2025-06-18', type: '로그인', subject: 'New login to Canva' },
      { date: '2024-03-20', type: '가입', subject: 'Welcome to Canva' },
    ],
  },
  {
    id: 'coupang',
    service: '쿠팡',
    category: '쇼핑',
    email: CONNECTED_EMAIL,
    signupDate: '2018-05-09',
    lastLogin: '2026-09-27',
    subscription: { plan: '와우 멤버십', monthly: 7890, nextBilling: '2026-10-09' },
    unused: false,
    securityAlert: null,
    permissions: [],
    automatable: true,
    recommended: null,
    signals: [
      { date: '2026-09-09', type: '결제', subject: '와우 멤버십 결제 안내' },
      { date: '2026-09-27', type: '결제', subject: '주문하신 상품이 배송되었습니다' },
      { date: '2018-05-09', type: '가입', subject: '쿠팡 회원가입을 축하합니다' },
    ],
  },
  {
    id: 'yanolja',
    service: '야놀자',
    category: '여행',
    email: CONNECTED_EMAIL,
    signupDate: '2020-08-01',
    lastLogin: '2023-07-22',
    subscription: null,
    unused: true,
    securityAlert: null,
    permissions: [],
    automatable: true,
    blocker: '탈퇴 단계에서 휴대폰 본인인증을 요구합니다',
    manualSteps: ['야놀자 앱 또는 웹에 로그인', '내 정보 > 설정 > 회원 탈퇴', '휴대폰 본인인증 후 탈퇴 확인'],
    recommended: '탈퇴',
    signals: [
      { date: '2025-08-01', type: '보안', subject: '[야놀자] 장기 미이용 계정 휴면 전환 예정 안내' },
      { date: '2023-07-22', type: '결제', subject: '예약이 확정되었습니다' },
      { date: '2020-08-01', type: '가입', subject: '야놀자 가입 완료' },
    ],
  },
  {
    id: 'ably',
    service: '에이블리',
    category: '쇼핑',
    email: CONNECTED_EMAIL,
    signupDate: '2022-01-15',
    lastLogin: '2024-02-10',
    subscription: null,
    unused: true,
    securityAlert: null,
    permissions: ['Google 계정 기본 정보'],
    automatable: true,
    recommended: '탈퇴',
    signals: [
      { date: '2024-02-10', type: '로그인', subject: '로그인 인증번호 안내' },
      { date: '2022-01-15', type: '가입', subject: '에이블리 가입을 환영해요' },
    ],
  },
  {
    id: 'inflearn',
    service: '인프런',
    category: '교육',
    email: CONNECTED_EMAIL,
    signupDate: '2023-03-04',
    lastLogin: '2026-08-30',
    subscription: null,
    unused: false,
    securityAlert: null,
    permissions: ['Google 계정 기본 정보'],
    automatable: true,
    recommended: null,
    signals: [
      { date: '2026-08-30', type: '인증', subject: '이메일 인증을 완료해주세요' },
      { date: '2023-03-04', type: '가입', subject: '인프런 가입을 환영합니다' },
    ],
  },
  {
    id: 'dropbox',
    service: 'Dropbox',
    category: '클라우드',
    email: CONNECTED_EMAIL,
    signupDate: '2017-10-02',
    lastLogin: '2022-12-01',
    subscription: null,
    unused: true,
    securityAlert: '2024년 개인정보 유출 사고 대상 서비스',
    permissions: ['Google 계정 기본 정보', 'Google 연락처 읽기'],
    automatable: true,
    recommended: '권한 해제',
    signals: [
      { date: '2024-05-02', type: '보안', subject: 'Important security notice about your account' },
      { date: '2022-12-01', type: '로그인', subject: 'New sign-in to Dropbox' },
      { date: '2017-10-02', type: '가입', subject: 'Welcome to Dropbox' },
    ],
  },
  {
    id: 'linkedin',
    service: 'LinkedIn',
    category: '커리어',
    email: CONNECTED_EMAIL,
    signupDate: '2023-09-10',
    lastLogin: '2026-09-18',
    subscription: null,
    unused: false,
    securityAlert: '비밀번호 재설정 요청이 감지됨 (본인 요청 아님일 수 있음)',
    permissions: [],
    automatable: false,
    manualSteps: ['LinkedIn 로그인', '설정 및 개인정보 > 계정 기본 설정 > 계정 해지', '해지 사유 선택 후 비밀번호 입력'],
    recommended: null,
    signals: [
      { date: '2026-09-18', type: '보안', subject: 'Password reset request' },
      { date: '2023-09-10', type: '가입', subject: 'Welcome to LinkedIn' },
    ],
  },
  {
    id: 'baemin',
    service: '배달의민족',
    category: '배달',
    email: CONNECTED_EMAIL,
    signupDate: '2019-06-21',
    lastLogin: '2026-09-26',
    subscription: null,
    unused: false,
    securityAlert: null,
    permissions: [],
    automatable: true,
    recommended: null,
    signals: [
      { date: '2026-09-26', type: '결제', subject: '주문이 접수되었습니다' },
      { date: '2019-06-21', type: '가입', subject: '배민 가입 완료' },
    ],
  },
  {
    id: '11st',
    service: '11번가',
    category: '쇼핑',
    email: CONNECTED_EMAIL,
    signupDate: '2016-04-30',
    lastLogin: null,
    subscription: null,
    unused: true,
    securityAlert: null,
    permissions: [],
    automatable: false,
    manualSteps: ['11번가 로그인 (휴면 계정이면 휴면 해제 먼저)', '나의 11번가 > 회원정보 > 회원탈퇴', '탈퇴 사유 선택 후 확인'],
    recommended: '탈퇴',
    signals: [
      { date: '2024-04-30', type: '보안', subject: '[11번가] 휴면계정 전환 안내' },
      { date: '2016-04-30', type: '가입', subject: '11번가 회원가입 완료' },
    ],
  },
  {
    id: 'notion',
    service: 'Notion',
    category: '생산성',
    email: CONNECTED_EMAIL,
    signupDate: '2021-09-01',
    lastLogin: '2026-09-28',
    subscription: null,
    unused: false,
    securityAlert: null,
    permissions: ['Google 계정 기본 정보', 'Google Calendar 읽기'],
    automatable: true,
    recommended: null,
    signals: [
      { date: '2026-09-28', type: '로그인', subject: 'Login code for Notion' },
      { date: '2021-09-01', type: '가입', subject: 'Welcome to Notion' },
    ],
  },
  {
    id: 'quizapp',
    service: '심리테스트 앱',
    category: '기타',
    email: CONNECTED_EMAIL,
    signupDate: '2022-05-05',
    lastLogin: '2022-05-05',
    subscription: null,
    unused: true,
    securityAlert: null,
    permissions: ['Google 계정 기본 정보', 'Google 연락처 읽기', 'Gmail 읽기'],
    automatable: true,
    recommended: '권한 해제',
    signals: [{ date: '2022-05-05', type: '가입', subject: '앱이 Google 계정에 액세스할 수 있습니다' }],
  },
]

export const PACK = { count: 5, price: 2900 }
