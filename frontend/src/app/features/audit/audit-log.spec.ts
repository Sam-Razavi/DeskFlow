import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AuditEntry } from '../../core/tickets/ticket.models';
import { afterDebounce, makeUser, respond } from '../tickets/testing';
import { AuditLog } from './audit-log';

const entry = (overrides: Partial<AuditEntry> = {}): AuditEntry => ({
  id: 1,
  actor: { id: 2, full_name: 'Alan Agent' },
  entity_type: 'ticket',
  entity_id: 7,
  action: 'status_changed',
  changes: { status: ['new', 'in_progress'] },
  created_at: '2026-09-02T09:30:15Z',
  ...overrides,
});

const FACETS = {
  entity_types: ['article', 'asset', 'ticket'],
  actions: ['created', 'status_changed'],
};

type Fixture = ReturnType<typeof TestBed.createComponent<AuditLog>>;

async function setup(page = { items: [entry()], total: 1 }) {
  TestBed.configureTestingModule({
    imports: [AuditLog],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  });
  const fixture = TestBed.createComponent(AuditLog);
  const http = TestBed.inject(HttpTestingController);
  await respond(http, '/api/audit-logs/facets', FACETS);
  await respond(http, '/api/users', [makeUser('agent'), makeUser('requester')]);
  await respond(http, '/api/audit-logs', page);
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
  return { fixture, http, el: fixture.nativeElement as HTMLElement };
}

// The form is internal to the component; the tests drive it the way the inputs would.
const form = (fixture: Fixture) =>
  (fixture.componentInstance as unknown as { filters: import('@angular/forms').FormGroup }).filters;

describe('AuditLog', () => {
  it('lists entries with who, what, which record and a readable summary', async () => {
    const { el } = await setup({
      items: [
        entry(),
        entry({
          id: 2,
          actor: null,
          entity_type: 'asset',
          entity_id: 3,
          action: 'assigned',
          changes: { assigned_to_id: [null, 1], status: ['in_stock', 'assigned'] },
        }),
      ],
      total: 2,
    });

    const rows = [...el.querySelectorAll('tr[mat-row]')].map((r) =>
      r.textContent!.replace(/\s+/g, ' '),
    );
    expect(rows[0]).toContain('Alan Agent');
    expect(rows[0]).toContain('status changed');
    expect(rows[0]).toContain('ticket #7');
    expect(rows[0]).toContain('status: new → in progress');
    expect(rows[1]).toContain('System');
    expect(rows[1]).toContain('asset #3');
    // User ids are shown as names (the requester in the fixture has id 1).
    expect(rows[1]).toContain('assigned to: — → Grace User');
  });

  it('links each record to its page, and shows the raw record on request', async () => {
    const { el } = await setup();
    expect(el.querySelector('tr[mat-row] a.link')!.getAttribute('href')).toBe('/tickets/7');
    const raw = el.querySelector('details.raw')!;
    expect(raw.querySelector('summary')!.textContent).toBe('Raw');
    expect(JSON.parse(raw.querySelector('pre')!.textContent!)).toEqual({
      status: ['new', 'in_progress'],
    });
  });

  it('does not link a deleted record or offer raw JSON for an entry with no details', async () => {
    const { el } = await setup({
      items: [entry({ entity_type: 'article', action: 'deleted', changes: {} })],
      total: 1,
    });
    expect(el.querySelector('tr[mat-row] a.link')).toBeNull();
    expect(el.querySelector('tr[mat-row]')!.textContent).toContain('article #7');
    expect(el.querySelector('details.raw')).toBeNull();
  });

  it('shows a removed record as plain text marked deleted, and a demo reset readably', async () => {
    const { el } = await setup({
      items: [
        entry({ record_exists: false }),
        entry({
          id: 2,
          actor: null,
          entity_type: 'demo',
          entity_id: 0,
          action: 'reset',
          changes: { tickets_removed: 20, tickets_created: 20 },
          record_exists: false,
        }),
      ],
      total: 2,
    });
    const rows = [...el.querySelectorAll('tr[mat-row]')];
    expect(el.querySelector('tr[mat-row] a.link')).toBeNull();
    expect(rows[0].textContent).toContain('ticket #7');
    expect(rows[0].querySelector('.gone')!.textContent).toBe('deleted');
    const reset = rows[1].textContent!.replace(/\s+/g, ' ');
    expect(reset).toContain('System');
    expect(reset).toContain('reset');
    expect(reset).not.toContain('#0');
    expect(reset).toContain('tickets removed: 20; tickets created: 20');
    expect(rows[1].querySelector('.gone')).toBeNull();
  });

  it('shows every filter choice that exists in the log', async () => {
    const { el } = await setup();
    const labels = [...el.querySelectorAll('mat-label')].map((l) => l.textContent?.trim());
    expect(labels).toEqual(['Record type', 'Action', 'Done by', 'Record #', 'From', 'To']);
  });

  it('sends the filters to the server after a short pause and goes back to page one', async () => {
    const { fixture, http } = await setup();
    form(fixture).patchValue({
      entityType: 'ticket',
      action: 'status_changed',
      actorId: 2,
      entityId: 7,
      from: '2026-09-01',
      to: '2026-09-30',
    });
    await afterDebounce(350);
    const req = await respond(http, '/api/audit-logs', { items: [], total: 0 });
    const p = req.request.params;
    expect([p.get('entity_type'), p.get('action'), p.get('actor_id'), p.get('entity_id')]).toEqual([
      'ticket',
      'status_changed',
      '2',
      '7',
    ]);
    expect([p.get('from'), p.get('to'), p.get('offset')]).toEqual([
      '2026-09-01',
      '2026-09-30',
      '0',
    ]);
  });

  it('treats an emptied record number as no filter', async () => {
    const { fixture, http } = await setup();
    form(fixture).patchValue({ entityId: Number.NaN });
    await afterDebounce(350);
    const req = await respond(http, '/api/audit-logs', { items: [], total: 0 });
    expect(req.request.params.has('entity_id')).toBe(false);
  });

  it('explains an empty result differently when filters are on, and can clear them', async () => {
    const { fixture, http, el } = await setup({ items: [], total: 0 });
    expect(el.textContent).toContain('Nothing has been recorded yet.');

    form(fixture).patchValue({ action: 'created' });
    await afterDebounce(350);
    await respond(http, '/api/audit-logs', { items: [], total: 0 });
    await fixture.whenStable();
    expect(el.textContent).toContain('No entries match these filters.');

    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Clear'))!.click();
    await afterDebounce(350);
    const req = await respond(http, '/api/audit-logs', { items: [], total: 0 });
    expect(req.request.params.has('action')).toBe(false);
  });

  it('still works when the dropdown lookups fail', async () => {
    TestBed.configureTestingModule({
      imports: [AuditLog],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const fixture = TestBed.createComponent(AuditLog);
    const http = TestBed.inject(HttpTestingController);
    await respond(http, '/api/audit-logs/facets', null, { status: 500, statusText: 'Error' });
    await respond(http, '/api/users', null, { status: 500, statusText: 'Error' });
    await respond(http, '/api/audit-logs', { items: [entry()], total: 1 });
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('tr[mat-row]').length).toBe(1);
    expect(el.querySelector('[role=alert]')).toBeNull();
    // Without the user list an id falls back to a readable placeholder.
    expect(el.textContent).toContain('status: new → in progress');
  });

  it('offers a retry when loading fails', async () => {
    TestBed.configureTestingModule({
      imports: [AuditLog],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const fixture = TestBed.createComponent(AuditLog);
    const http = TestBed.inject(HttpTestingController);
    await respond(http, '/api/audit-logs/facets', FACETS);
    await respond(http, '/api/users', []);
    await respond(http, '/api/audit-logs', null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Could not load the audit log');

    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Retry'))!.click();
    await respond(http, '/api/audit-logs', { items: [], total: 0 });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')).toBeNull();
  });
});

describe('AuditLog export', () => {
  const clicked: HTMLAnchorElement[] = [];

  beforeEach(() => {
    clicked.length = 0;
    URL.createObjectURL = vi.fn(() => 'blob:audit');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this);
    });
  });

  afterEach(() => vi.restoreAllMocks());

  const exportButton = (el: HTMLElement) =>
    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Export CSV'))!;

  it('downloads a CSV of the current filters, ignoring paging', async () => {
    const { fixture, http, el } = await setup();
    form(fixture).patchValue({ action: 'created', from: '2026-09-01' });
    await afterDebounce(350);
    await respond(http, '/api/audit-logs', { items: [], total: 0 });

    exportButton(el).click();
    const req = await respond(
      http,
      '/api/audit-logs/export.csv',
      new Blob(['id\r\n'], { type: 'text/csv' }),
    );
    expect(req.request.params.get('action')).toBe('created');
    expect(req.request.params.get('from')).toBe('2026-09-01');
    expect(req.request.params.has('limit')).toBe(false);
    await fixture.whenStable();

    expect(clicked.length).toBe(1);
    expect(clicked[0].download).toMatch(/^audit-log-\d{4}-\d{2}-\d{2}\.csv$/);
    expect(clicked[0].href).toBe('blob:audit');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:audit');
  });

  it('says so when the export fails, and downloads nothing', async () => {
    const { fixture, http, el } = await setup();
    exportButton(el).click();
    await respond(http, '/api/audit-logs/export.csv', null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('export failed');
    expect(clicked.length).toBe(0);
  });
});
