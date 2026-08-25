/**
 * API client for the CRM Vocal fallback UI.
 *
 * In dev, Next.js rewrites /api/* → FastAPI backend (localhost:8000).
 * Falls back to direct fetch if the backend is unavailable.
 */

const API_BASE = '/api';

export interface Participant {
  name: string;
  phone_number: string | null;
  role: string;
  side: 'left' | 'right';
}

export interface TaskItem {
  title: string;
  owner: string;
  deadline: string | null;
  difficulty: 'facile' | 'difficile' | 'très difficile' | null;
  model_hint: 'gpt-4o-mini' | 'claude-sonnet-4-6' | 'claude-opus-4-6' | null;
}

export interface PV {
  pv_id: string;
  call_date: string | null;
  call_type: '#appel-commercial' | '#appel-tech';
  left: Participant;
  right: Participant;
  additional_participants?: Participant[];
  subject: string;
  compte_rendu: string;
  actions: TaskItem[];
  meeting_created: boolean;
  meeting_datetime: string | null;
}

export interface PVSummary {
  pv_id: string;
  call_date: string;
  call_type: string;
  subject: string;
  left: string;
  right: string;
  additional_participants?: string[];
  task_count: number;
  meeting_created: boolean;
  stored_at: string;
}

export interface TodoItem {
  pv_id: string;
  pv_subject: string;
  call_date: string;
  title: string;
  owner: string;
  deadline: string | null;
  difficulty: string | null;
  model_hint: string | null;
}

export interface ListResponse<T> {
  count: number;
  [key: string]: T[] | number; // pvs or todos
}

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── PVs ──────────────────────────────────────────────────────────────────

export async function listPVs(callType?: string): Promise<PVSummary[]> {
  const params = callType ? `?call_type=${encodeURIComponent(callType)}` : '';
  const data = await fetchJSON<ListResponse<PVSummary>>(
    `${API_BASE}/fallback/pvs${params}`
  );
  return (data.pvs || []) as PVSummary[];
}

export async function getPV(pvId: string): Promise<PV> {
  return fetchJSON<PV>(`${API_BASE}/fallback/pvs/${encodeURIComponent(pvId)}`);
}

// ── Todos ────────────────────────────────────────────────────────────────

export async function listTodos(pvId?: string): Promise<TodoItem[]> {
  const params = pvId ? `?pv_id=${encodeURIComponent(pvId)}` : '';
  const data = await fetchJSON<ListResponse<TodoItem>>(
    `${API_BASE}/fallback/todos${params}`
  );
  return (data.todos || []) as TodoItem[];
}

// ── Health ───────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<{
  status: string;
  version: string;
  deepseek_configured: boolean;
}> {
  return fetchJSON(`${API_BASE}/health`);
}
