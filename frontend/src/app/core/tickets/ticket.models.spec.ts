import { nextStatuses, transitionLabel } from './ticket.models';

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
