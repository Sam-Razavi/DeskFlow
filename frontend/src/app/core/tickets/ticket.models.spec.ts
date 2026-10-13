import { describeDeadline, nextStatuses, transitionLabel } from './ticket.models';

describe('ticket workflow helpers', () => {
  it('offers staff every valid transition', () => {
    expect(nextStatuses('new', 'agent')).toEqual(['in_progress', 'pending', 'resolved', 'closed']);
    expect(nextStatuses('in_progress', 'admin')).toEqual(['pending', 'resolved']);
  });

  it('treats closed as terminal', () => {
    expect(nextStatuses('closed', 'admin')).toEqual([]);
  });

  it('only lets requesters confirm or reopen a resolved ticket', () => {
    expect(nextStatuses('resolved', 'requester')).toEqual(['in_progress', 'closed']);
    expect(nextStatuses('new', 'requester')).toEqual([]);
    expect(nextStatuses('in_progress', 'requester')).toEqual([]);
  });

  it('words buttons by context', () => {
    expect(transitionLabel('resolved', 'in_progress')).toBe('Reopen');
    expect(transitionLabel('resolved', 'closed')).toBe('Confirm & close');
    expect(transitionLabel('new', 'in_progress')).toBe('Mark in progress');
  });
});

describe('describeDeadline', () => {
  const now = new Date('2026-09-01T12:00:00Z');
  const at = (offsetMinutes: number) => new Date(now.getTime() + offsetMinutes * 60_000);

  it('counts down to a future deadline', () => {
    expect(describeDeadline(at(45), now)).toBe('due in 45m');
    expect(describeDeadline(at(135), now)).toBe('due in 2h 15m');
    expect(describeDeadline(at(180), now)).toBe('due in 3h');
  });

  it('switches to days beyond two days', () => {
    expect(describeDeadline(at(60 * 47), now)).toBe('due in 47h');
    expect(describeDeadline(at(60 * 50), now)).toBe('due in 2d 2h');
  });

  it('reports how long ago a deadline passed', () => {
    expect(describeDeadline(at(-30), now)).toBe('overdue by 30m');
    expect(describeDeadline(at(-200), now)).toBe('overdue by 3h 20m');
  });

  it('does not show zero minutes', () => {
    expect(describeDeadline(at(0.5), now)).toBe('due in under a minute');
  });
});
