import { Role } from '../auth/auth.models';

export type TicketStatus = 'new' | 'in_progress' | 'pending' | 'resolved' | 'closed';
export type Priority = 'p1' | 'p2' | 'p3' | 'p4';
export type Category = 'hardware' | 'software' | 'network' | 'access' | 'other';

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
}

export interface TicketFilters {
  status?: TicketStatus;
  priority?: Priority;
  category?: Category;
  q?: string;
  unassigned?: boolean;
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
