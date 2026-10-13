import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatSelect } from '@angular/material/select';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { Asset } from '../../core/assets/asset.models';
import { Role } from '../../core/auth/auth.models';
import { authStub, makeAsset, respond } from './testing';
import { TicketAssets } from './ticket-assets';

const laptop = makeAsset({ id: 1, asset_tag: 'DF-00001' });
const monitor = makeAsset({ id: 2, asset_tag: 'DF-00002', type: 'monitor', model: 'U2723' });

async function setup(
  role: Role,
  { linked = [] as Asset[], mine = [laptop, monitor], closed = false } = {},
) {
  TestBed.configureTestingModule({
    imports: [TicketAssets],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(TicketAssets);
  fixture.componentRef.setInput('ticketId', 7);
  fixture.componentRef.setInput('requesterId', 1);
  fixture.componentRef.setInput('closed', closed);
  const http = TestBed.inject(HttpTestingController);
  const assetsReq = respond(http, '/api/assets', { items: mine, total: mine.length });
  await respond(http, '/api/tickets/7/assets', linked);
  const list = await assetsReq;
  // The component handles the responses in a few promise hops; let them finish before looking.
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
  return { fixture, http, list, el: fixture.nativeElement as HTMLElement };
}

const pick = (fixture: ComponentFixture<TicketAssets>, asset: Asset) =>
  fixture.debugElement
    .query(By.directive(MatSelect))
    .componentInstance.selectionChange.emit({ value: asset });

describe('TicketAssets', () => {
  it('lets staff pick from the requester’s equipment, excluding what is already linked', async () => {
    const { el, list, fixture } = await setup('agent', { linked: [laptop] });
    expect(list.request.params.get('assigned_to_id')).toBe('1'); // scoped to the ticket's requester
    expect(el.textContent).toContain('DF-00001');
    expect(el.querySelector('mat-select')).not.toBeNull();

    // Only the monitor is left to link.
    fixture.debugElement.query(By.directive(MatSelect)).componentInstance.open();
    await fixture.whenStable();
    const options = [...document.querySelectorAll('mat-option')].map((o) => o.textContent);
    expect(options.join()).toContain('DF-00002');
    expect(options.join()).not.toContain('DF-00001');
  });

  it('links equipment and shows it straight away', async () => {
    const { fixture, http, el } = await setup('agent');
    pick(fixture, monitor);

    const req = await respond(http, '/api/tickets/7/assets/2', monitor);
    expect(req.request.method).toBe('PUT');
    await fixture.whenStable();
    expect(el.querySelector('.list')?.textContent).toContain('DF-00002');
  });

  it('unlinks equipment', async () => {
    const { fixture, http, el } = await setup('agent', { linked: [laptop] });
    el.querySelector<HTMLButtonElement>('button[aria-label="Unlink DF-00001"]')!.click();

    const req = await respond(http, '/api/tickets/7/assets/1', {});
    expect(req.request.method).toBe('DELETE');
    await fixture.whenStable();
    expect(el.querySelector('.list')?.textContent).not.toContain('DF-00001');
    expect(el.textContent).toContain('No equipment linked.');
  });

  it('reports a failed change without altering the list', async () => {
    const { fixture, http, el } = await setup('agent', { linked: [laptop] });
    el.querySelector<HTMLButtonElement>('button[aria-label="Unlink DF-00001"]')!.click();
    await respond(http, '/api/tickets/7/assets/1', null, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(el.querySelector('[role=alert]')?.textContent).toContain('could not be saved');
    expect(el.querySelector('.list')?.textContent).toContain('DF-00001');
  });

  it('is read-only once the ticket is closed', async () => {
    const { el } = await setup('agent', { linked: [laptop], closed: true });
    expect(el.textContent).toContain('DF-00001');
    expect(el.querySelector('mat-select')).toBeNull();
    expect(el.querySelector('button[aria-label="Unlink DF-00001"]')).toBeNull();
  });

  it('lets requesters link their own equipment, with no assignee filter sent', async () => {
    const { list, el } = await setup('requester', { mine: [laptop] });
    expect(list.request.params.has('assigned_to_id')).toBe(false); // the API already scopes it
    expect(el.querySelector('mat-select')).not.toBeNull();
  });

  it('hides the panel from a requester who has nothing to link', async () => {
    const { el } = await setup('requester', { mine: [] });
    expect(el.querySelector('mat-card')).toBeNull();
  });
});
