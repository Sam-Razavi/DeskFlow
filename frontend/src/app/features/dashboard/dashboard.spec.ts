import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Role } from '../../core/auth/auth.models';
import { DashboardSummary } from '../../core/dashboard/dashboard.service';
import { authStub, respond } from '../tickets/testing';
import { Dashboard } from './dashboard';

const summary: DashboardSummary = {
  open_total: 7,
  open_by_priority: { p1: 2, p2: 4, p3: 1, p4: 0 },
  sla_breached: 2,
  sla_at_risk: 0,
  unassigned: 3,
  assigned_to_me: 1,
  awaiting_confirmation: 5,
};

async function setup(role: Role, data: DashboardSummary = summary) {
  TestBed.configureTestingModule({
    imports: [Dashboard],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(Dashboard);
  const http = TestBed.inject(HttpTestingController);
  await respond(http, '/api/dashboard', data);
  await fixture.whenStable();
  return { fixture, http, el: fixture.nativeElement as HTMLElement };
}

const tile = (el: HTMLElement, label: string) =>
  [...el.querySelectorAll<HTMLAnchorElement>('a.tile')].find((a) => a.textContent?.includes(label));

describe('Dashboard', () => {
  it('leads with the open ticket count', async () => {
    const { el } = await setup('agent');
    expect(el.querySelector('.hero')?.textContent).toContain('Open tickets');
    expect(el.querySelector('.hero__value')?.textContent?.trim()).toBe('7');
  });

  it('links each figure to the matching filtered ticket list', async () => {
    const { el } = await setup('agent');
    expect(tile(el, 'SLA breached')!.getAttribute('href')).toBe('/tickets?sla=breached');
    expect(tile(el, 'Unassigned')!.getAttribute('href')).toBe('/tickets?assignment=unassigned');
    expect(tile(el, 'Assigned to me')!.getAttribute('href')).toBe('/tickets?assignment=mine');
    expect(tile(el, 'Awaiting confirmation')!.getAttribute('href')).toBe(
      '/tickets?status=resolved',
    );
  });

  it('only uses status colour (and its icon) when there is something to act on', async () => {
    const { el } = await setup('agent');
    const breached = tile(el, 'SLA breached')!;
    expect(breached.classList).toContain('tile--critical');
    expect(breached.querySelector('mat-icon')).not.toBeNull();

    const atRisk = tile(el, 'SLA at risk')!; // zero
    expect(atRisk.classList).not.toContain('tile--warning');
    expect(atRisk.querySelector('mat-icon')).toBeNull();
  });

  it('draws one bar per priority with the value at the tip', async () => {
    const { el } = await setup('agent');
    const rows = [...el.querySelectorAll('.bar-row')];
    expect(rows.map((r) => r.querySelector('.bar-row__value')!.textContent)).toEqual([
      '2',
      '4',
      '1',
      '0',
    ]);
    // P2 is the largest and gets the longest bar; P4 has none.
    const widths = rows.map((r) => (r.querySelector('.bar') as HTMLElement).style.width);
    expect(widths[1]).toBe('85%');
    expect(widths[3]).toBe('0%');
  });

  it('offers the same numbers as a table', async () => {
    const { fixture, el } = await setup('agent');
    [...el.querySelectorAll('button')]
      .find((b) => b.textContent?.includes('View as table'))!
      .click();
    await fixture.whenStable();

    const cells = [...el.querySelectorAll('.chart__table tbody tr')].map((r) => r.textContent);
    expect(cells[0]).toContain('P1 · Critical');
    expect(cells[0]).toContain('2');
    expect(el.querySelector('.bars')).toBeNull();
  });

  it('shows requesters only their own figures and no priority chart', async () => {
    const { el } = await setup('requester');
    expect(el.querySelectorAll('a.tile').length).toBe(1);
    expect(tile(el, 'Awaiting confirmation')).toBeDefined();
    expect(tile(el, 'SLA breached')).toBeUndefined();
    expect(el.querySelector('.chart')).toBeNull();
  });

  it('can retry after a failure', async () => {
    TestBed.configureTestingModule({
      imports: [Dashboard],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        authStub('agent'),
      ],
    });
    const fixture = TestBed.createComponent(Dashboard);
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    await respond(http, '/api/dashboard', null, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Could not load');

    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Retry'))!.click();
    await respond(http, '/api/dashboard', summary);
    await fixture.whenStable();
    expect(el.querySelector('.hero__value')?.textContent?.trim()).toBe('7');
  });
});
