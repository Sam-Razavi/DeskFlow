import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { makeAsset, respond } from '../tickets/testing';
import { AssetForm } from './asset-form';

function setup(id?: string) {
  TestBed.configureTestingModule({
    imports: [AssetForm],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  });
  const fixture = TestBed.createComponent(AssetForm);
  if (id) fixture.componentRef.setInput('id', id);
  const el = fixture.nativeElement as HTMLElement;
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  return { fixture, el, navigate, http: TestBed.inject(HttpTestingController) };
}

const field = (el: HTMLElement, name: string) =>
  el.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[formcontrolname="${name}"]`)!;

async function fill(fixture: ReturnType<typeof setup>['fixture'], values: Record<string, string>) {
  const el = fixture.nativeElement as HTMLElement;
  await fixture.whenStable(); // the first render is what wires the inputs to their form controls
  for (const [name, value] of Object.entries(values)) {
    const input = field(el, name);
    input.value = value;
    input.dispatchEvent(new Event('input'));
  }
  await fixture.whenStable();
}

const submitButton = (el: HTMLElement) =>
  el.querySelector<HTMLButtonElement>('button[type=submit]')!;

describe('AssetForm', () => {
  it('cannot be submitted until the required details are filled in', async () => {
    const { fixture, el } = setup();
    await fixture.whenStable();
    expect(submitButton(el).disabled).toBe(true);

    await fill(fixture, { manufacturer: 'Dell', model: 'Latitude 7440' });
    expect(submitButton(el).disabled).toBe(false);
  });

  it('creates an asset, sending blank optional fields as null so the tag is generated', async () => {
    const { fixture, el, http, navigate } = setup();
    await fill(fixture, { manufacturer: '  Dell ', model: 'Latitude 7440', serial_number: 'SN-1' });
    submitButton(el).click();

    const req = await respond(http, '/api/assets', makeAsset({ id: 42 }));
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      asset_tag: null,
      type: 'laptop',
      manufacturer: 'Dell',
      model: 'Latitude 7440',
      serial_number: 'SN-1',
      location: null,
      purchase_date: null,
      warranty_expires_on: null,
      notes: null,
    });
    await fixture.whenStable();
    expect(navigate).toHaveBeenCalledWith(['/assets', 42]);
  });

  it('rejects a warranty that ends before the purchase date', async () => {
    const { fixture, el } = setup();
    await fill(fixture, {
      manufacturer: 'Dell',
      model: 'X',
      purchase_date: '2026-06-01',
      warranty_expires_on: '2026-01-01',
    });
    expect(submitButton(el).disabled).toBe(true);

    await fill(fixture, { warranty_expires_on: '2029-06-01' });
    expect(submitButton(el).disabled).toBe(false);
  });

  it('explains a duplicate tag or serial number', async () => {
    const { fixture, el, http, navigate } = setup();
    await fill(fixture, { manufacturer: 'Dell', model: 'X', serial_number: 'SN-1' });
    submitButton(el).click();
    await respond(
      http,
      '/api/assets',
      { detail: 'exists' },
      { status: 409, statusText: 'Conflict' },
    );
    await fixture.whenStable();

    expect(el.querySelector('[role=alert]')?.textContent).toContain('already exists');
    expect(navigate).not.toHaveBeenCalled();
    expect(submitButton(el).disabled).toBe(false); // can correct it and retry
  });

  it('loads an existing asset for editing, locks its tag and saves only a patch', async () => {
    const { fixture, el, http, navigate } = setup('11');
    await respond(
      http,
      '/api/assets/11',
      makeAsset({ location: 'Floor 2', notes: 'Spare battery' }),
    );
    await fixture.whenStable();

    expect(el.querySelector('mat-card-title')?.textContent).toContain('Edit asset');
    expect(field(el, 'manufacturer').value).toBe('Dell');
    expect(field(el, 'asset_tag').value).toBe('DF-00011');
    expect(field(el, 'asset_tag').disabled).toBe(true);

    await fill(fixture, { location: '' });
    submitButton(el).click();
    const req = await respond(http, '/api/assets/11', makeAsset());
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.location).toBeNull(); // cleared, not left unchanged
    expect(req.request.body).not.toHaveProperty('asset_tag');
    await fixture.whenStable();
    expect(navigate).toHaveBeenCalledWith(['/assets', 11]);
  });
});
