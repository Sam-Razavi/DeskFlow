import { AuditEntry } from '../tickets/ticket.models';

const MAX_FIELDS = 4;
const MAX_VALUE_LENGTH = 60;

/** Where a record of each kind lives in the app. Records can be deleted, so not every link works. */
const RECORD_ROUTES: Record<string, string> = {
  ticket: '/tickets',
  asset: '/assets',
  article: '/kb',
};

export function recordLink(entry: AuditEntry): string[] | null {
  const base = RECORD_ROUTES[entry.entity_type];
  // A deleted record has nothing left to open.
  return base && entry.action !== 'deleted' ? [base, String(entry.entity_id)] : null;
}

export const humanize = (text: string) =>
  text
    .replace(/_id$/, '')
    .replace(/_/g, ' ')
    .replace(/\bsla\b/gi, 'SLA');

const ID_FIELDS = new Set(['assignee_id', 'assigned_to_id', 'requester_id', 'actor_id']);

/** Looks up a user's name from their id, or undefined when not known. */
export type NameOf = (userId: number) => string | undefined;

function formatValue(field: string, value: unknown, nameOf: NameOf): string {
  if (value === null || value === undefined || value === '') return '—';
  if (ID_FIELDS.has(field) && typeof value === 'number') {
    return nameOf(value) ?? `user #${value}`;
  }
  const text = typeof value === 'string' ? value.replace(/_/g, ' ') : JSON.stringify(value);
  return text.length > MAX_VALUE_LENGTH ? text.slice(0, MAX_VALUE_LENGTH - 1) + '…' : text;
}

function describeField(field: string, value: unknown, nameOf: NameOf): string {
  if (field === 'body_changed') return 'text edited';
  const label = humanize(field);
  if (Array.isArray(value) && value.length === 2) {
    return `${label}: ${formatValue(field, value[0], nameOf)} → ${formatValue(field, value[1], nameOf)}`;
  }
  return `${label}: ${formatValue(field, value, nameOf)}`;
}

/** A one-line summary of what changed. The full record is always available as raw JSON. */
export function describeChanges(entry: AuditEntry, nameOf: NameOf): string {
  const fields = Object.entries(entry.changes);
  if (fields.length === 0) return '';
  const shown = fields.slice(0, MAX_FIELDS).map(([f, v]) => describeField(f, v, nameOf));
  const more = fields.length - MAX_FIELDS;
  return more > 0 ? `${shown.join('; ')}; +${more} more` : shown.join('; ');
}
