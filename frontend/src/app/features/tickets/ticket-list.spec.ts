import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
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
});
