import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { FormGroupDirective } from '@angular/forms';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { Role } from '../../core/auth/auth.models';
import { Ticket } from '../../core/tickets/ticket.models';
import { TicketDetail } from './ticket-detail';
import { authStub, makeTicket, makeUser, respond } from './testing';

async function setup(role: Role, ticket: Ticket = makeTicket()) {
  TestBed.configureTestingModule({
    imports: [TicketDetail],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(TicketDetail);
  const http = TestBed.inject(HttpTestingController);
  fixture.componentRef.setInput('id', String(ticket.id));
  await respond(http, `/api/tickets/${ticket.id}`, ticket);
  await respond(http, `/api/tickets/${ticket.id}/comments`, [
    {
      id: 1,
      author: { id: 1, full_name: 'Grace User' },
      body: 'Any update?',
      is_internal: false,
      created_at: '2026-09-01T10:00:00Z',
    },
  ]);
  if (role !== 'requester') {
    await respond(http, `/api/tickets/${ticket.id}/history`, [
      {
        id: 1,
        actor: { id: 1, full_name: 'Grace User' },
        entity_type: 'ticket',
        entity_id: ticket.id,
        action: 'created',
        changes: {},
        created_at: '2026-09-01T09:00:00Z',
      },
    ]);
    await respond(http, '/api/users', [makeUser('agent'), makeUser('requester')]);
  }
  await fixture.whenStable();
  return { fixture, http, el: fixture.nativeElement as HTMLElement };
}

const button = (el: HTMLElement, text: string) =>
  [...el.querySelectorAll('button')].find((b) => b.textContent?.includes(text));

describe('TicketDetail', () => {
  it('shows the ticket, its conversation and staff-only history', async () => {
    const { el } = await setup('agent');
    expect(el.querySelector('h1')?.textContent).toContain('Laptop will not boot');
    expect(el.textContent).toContain('Any update?');
    expect(el.textContent).toContain('History');
    expect(el.textContent).toContain('created the ticket');
    expect(el.textContent).toContain('Internal note');
  });

  it('hides staff controls from requesters', async () => {
    const { el } = await setup('requester');
    expect(el.textContent).not.toContain('History');
    expect(el.textContent).not.toContain('Internal note');
    expect(el.querySelector('mat-select')).toBeNull();
    // Nothing a requester may do while the ticket is still being worked on.
    expect(button(el, 'Mark resolved')).toBeUndefined();
  });

  it('lets a requester confirm or reopen a resolved ticket', async () => {
    const { el } = await setup('requester', makeTicket({ status: 'resolved' }));
    expect(button(el, 'Confirm & close')).toBeDefined();
    expect(button(el, 'Reopen')).toBeDefined();
  });

  it('sends the status change and shows the updated ticket', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Mark resolved')!.click();

    const req = await respond(http, '/api/tickets/7/status', makeTicket({ status: 'resolved' }));
    expect(req.request.body).toEqual({ status: 'resolved' });
    await respond(http, '/api/tickets/7/comments', []);
    await respond(http, '/api/tickets/7/history', []);
    await fixture.whenStable();

    expect(el.querySelector('app-badge')?.textContent).toContain('Resolved');
  });

  it('shows the server message when a change is rejected', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Mark pending')!.click();
    const [req] = http.match((r) => r.url === '/api/tickets/7/status');
    req.flush({ detail: 'Cannot move ticket' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Cannot move ticket');
  });

  it('hides the reply form on closed tickets', async () => {
    const { el } = await setup('agent', makeTicket({ status: 'closed' }));
    expect(el.querySelector('textarea')).toBeNull();
    expect(el.textContent).toContain('This ticket is closed');
  });

  it('reports a missing ticket', async () => {
    TestBed.configureTestingModule({
      imports: [TicketDetail],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        authStub('requester'),
      ],
    });
    const fixture = TestBed.createComponent(TicketDetail);
    const http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('id', '99');
    await respond(http, '/api/tickets/99', null, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain("doesn't exist");
  });

  it('describes history entries with labels and names rather than raw values', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Mark resolved')!.click();
    await respond(http, '/api/tickets/7/status', makeTicket({ status: 'resolved' }));
    await respond(http, '/api/tickets/7/comments', []);
    await respond(http, '/api/tickets/7/history', [
      {
        id: 2,
        actor: { id: 2, full_name: 'Alan Agent' },
        entity_type: 'ticket',
        entity_id: 7,
        action: 'assigned',
        changes: { assignee_id: [null, 2], status: ['new', 'in_progress'] },
        created_at: '2026-09-01T09:05:00Z',
      },
    ]);
    await fixture.whenStable();

    const text = el.querySelector('.history')!.textContent;
    expect(text).toContain('assignee: unassigned → Alan Agent');
    expect(text).toContain('status: New → In progress');
  });

  it('clears the reply box without leaving it in an error state', async () => {
    const { fixture, http, el } = await setup('requester');
    const box = el.querySelector('textarea')!;
    box.value = 'Still broken';
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable(); // let the Post button become enabled
    button(el, 'Post')!.click();

    const req = await respond(http, '/api/tickets/7/comments', {
      id: 2,
      author: { id: 1, full_name: 'Grace User' },
      body: 'Still broken',
      is_internal: false,
      created_at: '2026-09-01T11:00:00Z',
    });
    expect(req.request.body).toEqual({ body: 'Still broken', is_internal: false });
    await respond(http, '/api/tickets/7/comments', []);
    await fixture.whenStable();

    expect(box.value).toBe('');
    // A lingering "submitted" flag is what makes Material paint the emptied box as an error.
    const form = fixture.debugElement.query(By.directive(FormGroupDirective));
    expect(form.injector.get(FormGroupDirective).submitted).toBe(false);
  });

  it('shows the service-level panel to staff with a live countdown', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-01T15:00:00Z'));
    try {
      const { el } = await setup(
        'agent',
        makeTicket({ response_sla: 'breached', resolution_sla: 'at_risk' }),
      );
      const panel = el.querySelector('.sla-card')!.textContent;
      expect(panel).toContain('Service level');
      expect(panel).toContain('Breached');
      expect(panel).toContain('overdue by 2h'); // response was due 13:00
      expect(panel).toContain('At risk');
      expect(panel).toContain('due in 2h'); // resolution due 17:00
    } finally {
      vi.useRealTimers();
    }
  });

  it('explains a paused clock and a reply that has already been given', async () => {
    const { el } = await setup(
      'agent',
      makeTicket({
        status: 'pending',
        sla_paused_at: '2026-09-01T10:00:00Z',
        resolution_sla: 'paused',
        response_sla: 'met',
        first_response_at: '2026-09-01T09:30:00Z',
      }),
    );
    const panel = el.querySelector('.sla-card')!.textContent;
    expect(panel).toContain('Clock paused while pending');
    expect(panel).toContain('Replied');
    expect(panel).toContain('Paused');
  });

  it('hides the service-level panel from requesters', async () => {
    const { el } = await setup('requester');
    expect(el.querySelector('.sla-card')).toBeNull();
  });

  it('words system SLA events in the history', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Mark resolved')!.click();
    await respond(http, '/api/tickets/7/status', makeTicket({ status: 'resolved' }));
    await respond(http, '/api/tickets/7/comments', []);
    await respond(http, '/api/tickets/7/history', [
      {
        id: 3,
        actor: null,
        entity_type: 'ticket',
        entity_id: 7,
        action: 'sla_breached',
        changes: { kind: 'resolution' },
        created_at: '2026-09-01T17:01:00Z',
      },
    ]);
    await fixture.whenStable();
    const text = el.querySelector('.history')!.textContent;
    expect(text).toContain('System');
    expect(text).toContain('SLA breached (resolution)');
  });

  it('still shows the ticket when a secondary request (the agent list) fails', async () => {
    TestBed.configureTestingModule({
      imports: [TicketDetail],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        authStub('agent'),
      ],
    });
    const fixture = TestBed.createComponent(TicketDetail);
    const http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('id', '7');

    // All four requests are issued together, so answer them in any order.
    await respond(http, '/api/users', null, { status: 500, statusText: 'Server Error' });
    await respond(http, '/api/tickets/7', makeTicket());
    await respond(http, '/api/tickets/7/comments', []);
    await respond(http, '/api/tickets/7/history', []);
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h1')?.textContent).toContain('Laptop will not boot');
    expect(el.textContent).not.toContain("doesn't exist");
  });
});
