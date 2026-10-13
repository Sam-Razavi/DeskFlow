import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatSelect } from '@angular/material/select';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { Asset } from '../../core/assets/asset.models';
import { Role } from '../../core/auth/auth.models';
import { authStub, makeAsset, makeTicket, makeUser, respond } from '../tickets/testing';
import { AssetDetail } from './asset-detail';

const history = [
  {
    id: 1,
    actor: { id: 2, full_name: 'Alan Agent' },
    entity_type: 'asset',
    entity_id: 11,
    action: 'created',
    changes: {},
    created_at: '2026-01-15T09:00:00Z',
  },
  {
    id: 2,
    actor: { id: 2, full_name: 'Alan Agent' },
    entity_type: 'asset',
    entity_id: 11,
    action: 'assigned',
    changes: { assigned_to_id: [null, 1], status: ['in_stock', 'assigned'] },
    created_at: '2026-01-16T09:00:00Z',
  },
  {
    id: 3,
    actor: { id: 2, full_name: 'Alan Agent' },
    entity_type: 'asset',
    entity_id: 11,
    action: 'ticket_linked',
    changes: { ticket_id: 7 },
    created_at: '2026-01-17T09:00:00Z',
  },
];

async function setup(role: Role, asset: Asset = makeAsset()) {
  TestBed.configureTestingModule({
    imports: [AssetDetail],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(AssetDetail);
  const http = TestBed.inject(HttpTestingController);
  fixture.componentRef.setInput('id', String(asset.id));
  await respond(http, `/api/assets/${asset.id}`, asset);
  if (role !== 'requester') {
    await respond(http, `/api/assets/${asset.id}/history`, history);
    await respond(http, `/api/assets/${asset.id}/tickets`, [
      makeTicket({ id: 7, title: 'Battery swelling' }),
    ]);
    await respond(http, '/api/users', [makeUser('requester'), makeUser('agent')]);
  }
  await fixture.whenStable();
  return { fixture, http, el: fixture.nativeElement as HTMLElement };
}

const button = (el: HTMLElement, text: string) =>
  [...el.querySelectorAll('button')].find((b) => b.textContent?.includes(text));

const pickAssignee = (fixture: ComponentFixture<AssetDetail>, value: number) =>
  fixture.debugElement
    .query(By.directive(MatSelect))
    .componentInstance.selectionChange.emit({ value });

describe('AssetDetail', () => {
  it('shows staff the details, linked tickets, history and controls', async () => {
    const { el } = await setup('agent');
    expect(el.querySelector('h1')?.textContent).toContain('DF-00011');
    expect(el.querySelector('h1')?.textContent).toContain('Dell Latitude 7440');
    expect(el.textContent).toContain('SN-1001');
    expect(el.textContent).toContain('Battery swelling');
    expect(el.textContent).toContain('Edit details');
    expect(button(el, 'Send for repair')).toBeDefined();
    expect(button(el, 'Retire')).toBeDefined();
  });

  it('words history entries with names and labels rather than raw ids', async () => {
    const { el } = await setup('agent');
    const text = el.querySelector('.history')!.textContent;
    expect(text).toContain('added the asset');
    expect(text).toContain('assigned to: — → Grace User');
    expect(text).toContain('status: in stock → assigned');
    expect(text).toContain('linked ticket #7');
  });

  it('shows requesters their equipment without controls, history or ticket links', async () => {
    const { el } = await setup('requester', makeAsset({ status: 'assigned' }));
    expect(el.querySelector('h1')?.textContent).toContain('DF-00011');
    expect(el.textContent).not.toContain('Edit details');
    expect(el.textContent).not.toContain('History');
    expect(el.textContent).not.toContain('Tickets about this asset');
    expect(el.querySelector('mat-select')).toBeNull();
    expect(button(el, 'Retire')).toBeUndefined();
  });

  it('assigns equipment to a person', async () => {
    const { fixture, http } = await setup('agent');
    pickAssignee(fixture, 1);

    const req = await respond(
      http,
      '/api/assets/11/assignment',
      makeAsset({ status: 'assigned', assigned_to: { id: 1, full_name: 'Grace User' } }),
    );
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ assigned_to_id: 1 });
  });

  it('returns equipment to stock by choosing "Nobody"', async () => {
    const { fixture, http } = await setup(
      'agent',
      makeAsset({ status: 'assigned', assigned_to: { id: 1, full_name: 'Grace User' } }),
    );
    pickAssignee(fixture, 0);
    const req = await respond(http, '/api/assets/11/assignment', makeAsset());
    expect(req.request.body).toEqual({ assigned_to_id: null });
  });

  it('only allows assignment while the equipment is in stock or already assigned', async () => {
    const { el } = await setup('agent', makeAsset({ status: 'in_repair' }));
    expect(el.querySelector('mat-select')).toBeNull();
    expect(button(el, 'Repaired, return to stock')).toBeDefined();
  });

  it('asks for confirmation before retiring, and lets you back out', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Retire')!.click();
    await fixture.whenStable();

    expect(el.textContent).toContain('Confirm: retire for good');
    http.expectNone('/api/assets/11/status'); // nothing sent yet

    button(el, 'Keep it')!.click();
    await fixture.whenStable();
    expect(button(el, 'Confirm: retire for good')).toBeUndefined();
  });

  it('retires on the second click and shows the result', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Retire')!.click();
    await fixture.whenStable();
    button(el, 'Confirm: retire for good')!.click();

    const req = await respond(http, '/api/assets/11/status', makeAsset({ status: 'retired' }));
    expect(req.request.body).toEqual({ status: 'retired' });
    await respond(http, '/api/assets/11/history', history);
    await respond(http, '/api/assets/11/tickets', []);
    await fixture.whenStable();
    expect(el.querySelector('app-asset-status')?.textContent).toContain('Retired');
    expect(button(el, 'Retire')).toBeUndefined(); // terminal: nothing further to offer
  });

  it('shows the server message when a change is refused', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Send for repair')!.click();
    await respond(
      http,
      '/api/assets/11/status',
      { detail: 'Cannot move asset' },
      { status: 409, statusText: 'Conflict' },
    );
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Cannot move asset');
  });

  it('reports a missing asset', async () => {
    TestBed.configureTestingModule({
      imports: [AssetDetail],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        authStub('requester'),
      ],
    });
    const fixture = TestBed.createComponent(AssetDetail);
    const http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('id', '99');
    await respond(http, '/api/assets/99', null, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain("doesn't exist");
  });

  it('still shows the asset when the optional extras fail to load', async () => {
    TestBed.configureTestingModule({
      imports: [AssetDetail],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        authStub('agent'),
      ],
    });
    const fixture = TestBed.createComponent(AssetDetail);
    const http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('id', '11');
    await respond(http, '/api/assets/11', makeAsset());
    await respond(http, '/api/assets/11/history', null, { status: 500, statusText: 'Error' });
    await respond(http, '/api/assets/11/tickets', []);
    await respond(http, '/api/users', null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).querySelector('h1')?.textContent).toContain(
      'DF-00011',
    );
  });
});
