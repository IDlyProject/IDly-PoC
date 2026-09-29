// 개발 환경에서는 vite 프록시를 거치고, 배포 환경에서는 같은 웹 백엔드를 호출한다.

import type { Account } from "./mock";

export type AuthMethod = "password" | "oauth_google" | "oauth_microsoft";

export interface Provider {
  id: string;
  name: string;
  domains: string[];
  host: string | null;
  auth: AuthMethod[];
  // 연동 전에 사용자가 할 일. url이 있으면 해당 설정 페이지로 보낸다
  steps: { text: string; url?: string }[];
  password_label: string | null;
  login_hint: string;
}

export interface SyncJob {
  id: string;
  email: string;
  status: "대기" | "받는 중" | "분석 중" | "완료" | "실패";
  // 분석 단계 이름 (헤더 분석 / 결제 메일 확인 / AI 판별)
  step: string | null;
  accounts_found: number | null;
  // 탐색하는 폴더 (스팸·휴지통·보낸편지함 제외)
  folders: string[];
  // 받은 메일 헤더 수 / 전체
  total: number;
  fetched: number;
  error: string | null;
}

// IDly 로그인 상태: IDly 계정과 그 계정에 연동된 메일함들
export interface Session {
  user: { email: string } | null;
  mailboxes: {
    email: string;
    provider: string;
    // 마지막 탐색이 끝난 시각 (저장된 결과가 있으면)
    scanned_at: string | null;
    // 서버에서 진행 중·최근 탐색 작업
    job_id: string | null;
  }[];
}

// 클라우드 브라우저 에이전트 작업 (backend/actions/runner.py)
export interface ActionRun {
  id: string;
  service: string;
  domain: string;
  action: string;
  // flow: 검증된 서비스별 흐름, ai: AI가 화면을 보며 메뉴를 찾아감
  mode: "flow" | "ai";
  status: "대기" | "진행 중" | "입력 필요" | "확인 필요" | "완료" | "실패" | "취소됨";
  step: number;
  steps: number;
  message: string;
  error: string | null;
  hasScreen: boolean;
}

// 원격 화면 입력
export type ActionInput =
  | { type: "click"; x: number; y: number }
  | { type: "type"; text: string }
  | { type: "key"; key: string }
  | { type: "scroll"; dy: number }
  | { type: "resume" | "confirm" | "cancel" };

// 메일에서 찾은 계정 (backend/analysis.py)
export interface DiscoveryReport {
  messages_scanned: number;
  candidates: number;
  ai_used: boolean;
  // AI 판별이 실패했을 때 이유 (보고서는 규칙 결과로 나온다)
  ai_error: string | null;
  model: string | null;
  accounts: Account[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok)
    throw new Error(body?.detail ?? "IDly 백엔드에 연결하지 못했습니다.");
  return body as T;
}

export const api = {
  health: () => request<{ ok: boolean }>("/api/health"),
  providers: () => request<Provider[]>("/api/providers"),
  me: () => request<Session>("/api/me"),
  signup: (email: string, password: string) =>
    request<Session>("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    request<Session>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<Session>("/api/auth/logout", { method: "POST" }),
  addMailbox: (body: {
    email: string;
    password: string;
    provider: string;
    host?: string;
    port?: number;
    username?: string;
    // OpenAI(국외) 전송 동의. 서버에 동의 시각이 저장된다
    consented: boolean;
  }) =>
    request<Session>("/api/mailboxes", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeMailbox: (email: string) =>
    request<Session>(`/api/mailboxes/${encodeURIComponent(email)}`, { method: "DELETE" }),
  mailboxReport: (email: string) =>
    request<DiscoveryReport>(`/api/mailboxes/${encodeURIComponent(email)}/report`),
  startSync: (email: string) =>
    request<SyncJob>("/api/sync", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  syncStatus: (id: string) => request<SyncJob>(`/api/sync/${id}`),
  startAction: (body: { domain: string; service: string; account_email: string; action: string }) =>
    request<ActionRun>("/api/actions", { method: "POST", body: JSON.stringify(body) }),
  actionStatus: (id: string) => request<ActionRun>(`/api/actions/${id}`),
  actionInput: (id: string, input: ActionInput) =>
    request<ActionRun>(`/api/actions/${id}/input`, { method: "POST", body: JSON.stringify(input) }),
  actionScreenUrl: (id: string, tick: number) => `/api/actions/${id}/screen?t=${tick}`,
  syncReport: (id: string) => request<DiscoveryReport>(`/api/sync/${id}/report`),
};
