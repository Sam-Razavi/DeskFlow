import { Role } from '../auth/auth.models';

export type TicketStatus = 'new' | 'in_progress' | 'pending' | 'resolved' | 'closed';
export type Priority = 'p1' | 'p2' | 'p3' | 'p4';
export type Category = 'hardware' | 'software' | 'network' | 'access' | 'other';

export type SlaState = 'ok' | 'at_risk' | 'breached' | 'met' | 'paused' | 'n/a';
export type SlaFilter = 'breached' | 'at_risk';
export type Assignment = 'unassigned' | 'mine';

export interface UserBrief {
  id: number;
  full_name: string;
}

export interface Ticket {
  id: number;
  title: string;
  description: string;
  status: TicketStatus;
  priority: Priority;
  category: Category;
  requester: UserBrief;
  assignee: UserBrief | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  first_response_at: string | null;
  response_due_at: string;
  resolution_due_at: string;
  sla_paused_at: string | null;
  response_sla: SlaState;
  resolution_sla: SlaState;
  /** The most urgent of the two, which is what list views show. */
  sla_state: SlaState;
}

export interface TicketPage {
  items: Ticket[];
  total: number;
}

export interface TicketComment {
  id: number;
  author: UserBrief;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  actor: UserBrief | null;
  entity_type: string;
  entity_id: number;
  action: string;
  changes: Record<string, unknown>;
  created_at: string;
  /** False when the record has since been removed (only the audit log list reports this). */
  record_exists?: boolean;
}

export interface TicketFilters {
  status?: TicketStatus;
  priority?: Priority;
  category?: Category;
  q?: string;
  unassigned?: boolean;
  assigneeId?: number;
  sla?: SlaFilter;
  limit: number;
  offset: number;
}

export interface NewTicket {
  title: string;
  description: string;
  priority: Priority;
  category: Category;
}

export const STATUSES: readonly TicketStatus[] = [
  'new',
  'in_progress',
  'pending',
  'resolved',
  'closed',
];
export const PRIORITIES: readonly Priority[] = ['p1', 'p2', 'p3', 'p4'];
export const CATEGORIES: readonly Category[] = [
  'hardware',
  'software',
  'network',
  'access',
  'other',
];

export const STATUS_LABELS: Record<TicketStatus, string> = {
  new: 'New',
  in_progress: 'In progress',
  pending: 'Pending',
  resolved: 'Resolved',
  closed: 'Closed',
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  p1: 'P1 · Critical',
  p2: 'P2 · High',
  p3: 'P3 · Medium',
  p4: 'P4 · Low',
};

export const CATEGORY_LABELS: Record<Category, string> = {
  hardware: 'Hardware',
  software: 'Software',
  network: 'Network',
  access: 'Access',
  other: 'Other',
};

// Mirrors backend/app/services/workflow.py. The API is the source of truth;
// this only decides which buttons to offer.
const TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  new: ['in_progress', 'pending', 'resolved', 'closed'],
  in_progress: ['pending', 'resolved'],
  pending: ['in_progress', 'resolved'],
  resolved: ['in_progress', 'closed'],
  closed: [],
};

export function nextStatuses(current: TicketStatus, role: Role): TicketStatus[] {
  const all = TRANSITIONS[current];
  return role === 'requester' ? all.filter(() => current === 'resolved') : all;
}

/** Wording for a status button, which depends on where the ticket is coming from. */
export function transitionLabel(from: TicketStatus, to: TicketStatus): string {
  if (from === 'resolved' && to === 'in_progress') return 'Reopen';
  if (from === 'resolved' && to === 'closed') return 'Confirm & close';
  return `Mark ${STATUS_LABELS[to].toLowerCase()}`;
}

export const SLA_LABELS: Record<SlaState, string> = {
  ok: 'On track',
  at_risk: 'At risk',
  breached: 'Breached',
  met: 'Met',
  paused: 'Paused',
  'n/a': 'Not applicable',
};

/** "due in 2h 15m" / "overdue by 3h", for a deadline relative to now. */
export function describeDeadline(due: Date, now: Date): string {
  const diffMs = due.getTime() - now.getTime();
  const total = formatDuration(Math.abs(diffMs));
  if (diffMs < 0) return `overdue by ${total}`;
  return `due in ${total}`;
}

function formatDuration(ms: number): string {
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return 'under a minute';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    const rest = minutes % 60;
    return rest ? `${hours}h ${rest}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days}d ${restHours}h` : `${days}d`;
}
