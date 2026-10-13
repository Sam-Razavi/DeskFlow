import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { Role } from '../../core/auth/auth.models';
import { authStub, makeAsset, respond } from '../tickets/testing';
import { AssetList } from './asset-list';

const labels = (el: HTMLElement) =>
  [...el.querySelectorAll('mat-label')].map((l) => l.textContent?.trim());

function setup(role: Role) {
  TestBed.configureTestingModule({
    imports: [AssetList],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(AssetList);
  return {
    fixture,
    http: TestBed.inject(HttpTestingController),
    el: fixture.nativeElement as HTMLElement,
  };
}

describe('AssetList', () => {
  it('lists assets for staff with status, assignee and a warranty warning', async () => {
    const { fixture, http, el } = setup('agent');
    await respond(http, '/api/assets', {
      items: [
        makeAsset({
          status: 'assigned',
          assigned_to: { id: 1, full_name: 'Grace User' },
          warranty_state: 'expiring',
          warranty_expires_on: '2026-10-20',
        }),
        makeAsset({ id: 12, asset_tag: 'DF-00012', status: 'in_repair' }),
      ],
      total: 2,
    });
    await fixture.whenStable();

    const rows = [...el.querySelectorAll('tr[mat-row]')];
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('DF-00011');
    expect(rows[0].textContent).toContain('Dell Latitude 7440');
    expect(rows[0].textContent).toContain('Assigned');
    expect(rows[0].textContent).toContain('Grace User');
    expect(rows[0].textContent).toContain('Expiring soon');
    expect(rows[1].textContent).toContain('In repair');
    expect(el.querySelector('h1')?.textContent).toContain('Assets');
    expect(el.textContent).toContain('New asset');
  });

  it('gives requesters a read-only "My equipment" view', async () => {
    const { fixture, http, el } = setup('requester');
    await respond(http, '/api/assets', { items: [makeAsset()], total: 1 });
    await fixture.whenStable();

    expect(el.querySelector('h1')?.textContent).toContain('My equipment');
    expect(el.textContent).not.toContain('New asset');
    expect(labels(el)).not.toContain('Status');
    const headers = [...el.querySelectorAll('th[mat-header-cell]')].map((h) =>
      h.textContent?.trim(),
    );
    expect(headers).not.toContain('Assigned to');
    expect(headers).not.toContain('Status');
  });

  it('shows role-appropriate empty states', async () => {
    const staff = setup('agent');
    await respond(staff.http, '/api/assets', { items: [], total: 0 });
    await staff.fixture.whenStable();
    expect(staff.el.textContent).toContain('No assets yet.');
    TestBed.resetTestingModule();

    const requester = setup('requester');
    await respond(requester.http, '/api/assets', { items: [], total: 0 });
    await requester.fixture.whenStable();
    expect(requester.el.textContent).toContain('No equipment is assigned to you.');
  });

  it('offers a retry when loading fails', async () => {
    const { fixture, http, el } = setup('agent');
    await respond(http, '/api/assets', null, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Could not load assets');

    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Retry'))!.click();
    await respond(http, '/api/assets', { items: [], total: 0 });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')).toBeNull();
  });
});

describe('AssetList deep links', () => {
  async function open(query: string) {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'assets', component: AssetList }]),
        authStub('agent'),
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const navigation = RouterTestingHarness.create().then((h) =>
      h.navigateByUrl('/assets' + query, AssetList),
    );
    const req = await respond(http, '/api/assets', { items: [], total: 0 });
    await navigation;
    return req.request.params;
  }

  it('applies filters from the query string so dashboard tiles land on the right list', async () => {
    const repair = await open('?status=in_repair');
    expect(repair.get('status')).toBe('in_repair');
    TestBed.resetTestingModule();

    const warranty = await open('?warranty=expiring');
    expect(warranty.get('warranty')).toBe('expiring');
  });

  it('ignores values that are not real options', async () => {
    const params = await open('?status=hacked&warranty=forever');
    expect(params.has('status')).toBe(false);
    expect(params.has('warranty')).toBe(false);
  });
});
