import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TicketList } from './ticket-list';
import { authStub, makeTicket, respond } from './testing';

function setup(role: 'requester' | 'agent' = 'agent') {
  TestBed.configureTestingModule({
    imports: [TicketList],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(TicketList);
  return {
    fixture,
    http: TestBed.inject(HttpTestingController),
    el: fixture.nativeElement as HTMLElement,
  };
}

const labels = (el: HTMLElement) =>
  [...el.querySelectorAll('mat-label')].map((l) => l.textContent?.trim());

describe('TicketList', () => {
  it('renders tickets returned by the API', async () => {
    const { fixture, http, el } = setup();
    await respond(http, '/api/tickets', {
      items: [makeTicket({ id: 1, title: 'VPN down', priority: 'p1' }), makeTicket({ id: 2 })],
      total: 2,
    });
    await fixture.whenStable();

    const rows = el.querySelectorAll('tr[mat-row]');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('VPN down');
    expect(rows[0].textContent).toContain('P1');
  });

  it('titles the page by role', async () => {
    const staff = setup('agent');
    await respond(staff.http, '/api/tickets', { items: [], total: 0 });
    await staff.fixture.whenStable();
    expect(staff.el.querySelector('h1')?.textContent).toContain('All tickets');
  });

  it('shows an empty state', async () => {
    const { fixture, http, el } = setup('requester');
    await respond(http, '/api/tickets', { items: [], total: 0 });
    await fixture.whenStable();
    expect(el.querySelector('h1')?.textContent).toContain('My tickets');
    expect(el.textContent).toContain('No tickets yet.');
  });

  it('offers a retry when loading fails', async () => {
    const { fixture, http, el } = setup();
    const req = http.expectOne((r) => r.url === '/api/tickets');
    req.flush(null, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(el.querySelector('[role=alert]')?.textContent).toContain('Could not load tickets');
    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Retry'))!.click();
    await respond(http, '/api/tickets', { items: [], total: 0 });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')).toBeNull();
  });

  it('shows the SLA column and filters to staff only', async () => {
    const staff = setup('agent');
    await respond(staff.http, '/api/tickets', {
      items: [makeTicket({ sla_state: 'breached' })],
      total: 1,
    });
    await staff.fixture.whenStable();
    expect(staff.el.textContent).toContain('Breached');
    expect(labels(staff.el)).toEqual(expect.arrayContaining(['SLA', 'Assigned to']));
    TestBed.resetTestingModule();

    const requester = setup('requester');
    await respond(requester.http, '/api/tickets', {
      items: [makeTicket({ sla_state: 'breached' })],
      total: 1,
    });
    await requester.fixture.whenStable();
    expect(requester.el.querySelector('app-sla-badge')).toBeNull();
    expect(labels(requester.el)).not.toContain('SLA');
    expect(labels(requester.el)).not.toContain('Assigned to');
    expect(labels(requester.el)).toContain('Status');
  });
});

describe('TicketList deep links', () => {
  async function open(query: string) {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'tickets', component: TicketList }]),
        authStub('agent'),
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const navigation = RouterTestingHarness.create().then((h) =>
      h.navigateByUrl('/tickets' + query, TicketList),
    );
    const req = await respond(http, '/api/tickets', { items: [], total: 0 });
    await navigation;
    return req.request.params;
  }

  it('applies filters from the query string so dashboard tiles land on the right list', async () => {
    const params = await open('?sla=breached&assignment=unassigned&status=resolved');
    expect(params.get('sla')).toBe('breached');
    expect(params.get('unassigned')).toBe('true');
    expect(params.get('status')).toBe('resolved');
  });

  it('filters by "mine" using the signed-in user id', async () => {
    const params = await open('?assignment=mine');
    expect(params.get('assignee_id')).toBe('2');
    expect(params.has('unassigned')).toBe(false);
  });

  it('ignores values that are not real options', async () => {
    const params = await open('?sla=bogus&status=hacked&assignment=everyone');
    expect(params.has('sla')).toBe(false);
    expect(params.has('status')).toBe(false);
    expect(params.has('unassigned')).toBe(false);
  });
});
