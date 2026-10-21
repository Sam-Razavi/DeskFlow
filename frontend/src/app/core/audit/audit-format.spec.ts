import { AuditEntry } from '../tickets/ticket.models';
import { describeChanges, humanize, recordGone, recordLabel, recordLink } from './audit-format';

const entry = (overrides: Partial<AuditEntry> = {}): AuditEntry => ({
  id: 1,
  actor: { id: 2, full_name: 'Alan Agent' },
  entity_type: 'ticket',
  entity_id: 7,
  action: 'updated',
  changes: {},
  created_at: '2026-09-01T09:00:00Z',
  ...overrides,
});

const names = (id: number) => ({ 3: 'Grace User' })[id as 3];

describe('describeChanges', () => {
  it('shows before and after for a change', () => {
    expect(describeChanges(entry({ changes: { status: ['new', 'in_progress'] } }), names)).toBe(
      'status: new → in progress',
    );
  });

  it('turns user ids into names, and falls back to the id for unknown users', () => {
    expect(describeChanges(entry({ changes: { assignee_id: [null, 3] } }), names)).toBe(
      'assignee: — → Grace User',
    );
    expect(describeChanges(entry({ changes: { assigned_to_id: [3, 99] } }), names)).toBe(
      'assigned to: Grace User → user #99',
    );
  });

  it('shows plain values for a creation and trims long ones', () => {
    const long = 'x'.repeat(200);
    const text = describeChanges(entry({ changes: { title: long } }), names);
    expect(text.startsWith('title: xxx')).toBe(true);
    expect(text.length).toBeLessThan(80);
    expect(text.endsWith('…')).toBe(true);
  });

  it('caps the number of fields and says how many were left out', () => {
    const changes = { a: 1, b: 2, c: 3, d: 4, e: 5, f: 6 };
    expect(describeChanges(entry({ changes }), names)).toBe('a: 1; b: 2; c: 3; d: 4; +2 more');
  });

  it('has a plain wording for an edited article body and nothing for an empty change', () => {
    expect(describeChanges(entry({ changes: { body_changed: true } }), names)).toBe('text edited');
    expect(describeChanges(entry({ changes: {} }), names)).toBe('');
  });

  it('prints nothing for missing values rather than "null"', () => {
    expect(describeChanges(entry({ changes: { location: [null, ''] } }), names)).toBe(
      'location: — → —',
    );
  });
});

describe('recordLink', () => {
  it('links each kind of record to its page', () => {
    expect(recordLink(entry({ entity_type: 'ticket', entity_id: 7 }))).toEqual(['/tickets', '7']);
    expect(recordLink(entry({ entity_type: 'asset', entity_id: 3 }))).toEqual(['/assets', '3']);
    expect(recordLink(entry({ entity_type: 'article', entity_id: 4 }))).toEqual(['/kb', '4']);
  });

  it('does not link a record that was deleted, or one it does not know', () => {
    expect(recordLink(entry({ entity_type: 'article', action: 'deleted' }))).toBeNull();
    expect(recordLink(entry({ entity_type: 'mystery' }))).toBeNull();
  });

  it('does not link a record the server says no longer exists', () => {
    const removed = entry({ entity_type: 'ticket', record_exists: false });
    expect(recordLink(removed)).toBeNull();
    expect(recordGone(removed)).toBe(true);
    expect(recordGone(entry({ entity_type: 'ticket', record_exists: true }))).toBe(false);
    // Not a record with a page: nothing to call deleted.
    expect(recordGone(entry({ entity_type: 'demo', entity_id: 0, record_exists: false }))).toBe(
      false,
    );
  });
});

describe('recordLabel', () => {
  it('names the record, or just the kind when the entry is about no single record', () => {
    expect(recordLabel(entry({ entity_type: 'ticket', entity_id: 7 }))).toBe('ticket #7');
    expect(recordLabel(entry({ entity_type: 'demo', entity_id: 0 }))).toBe('demo');
  });
});

describe('humanize', () => {
  it('reads field and action names as words', () => {
    expect(humanize('status_changed')).toBe('status changed');
    expect(humanize('assignee_id')).toBe('assignee');
    expect(humanize('sla_breached')).toBe('SLA breached');
    expect(humanize('sla_at_risk')).toBe('SLA at risk');
  });
});
