import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { Role } from '../../core/auth/auth.models';
import { afterDebounce, authStub, makeSummary, makeTicket, respond } from './testing';
import { TicketForm } from './ticket-form';

function setup(role: Role = 'requester') {
  TestBed.configureTestingModule({
    imports: [TicketForm],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(TicketForm);
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  return {
    fixture,
    navigate,
    http: TestBed.inject(HttpTestingController),
    el: fixture.nativeElement as HTMLElement,
  };
}

async function type(fixture: ReturnType<typeof setup>['fixture'], name: string, value: string) {
  await fixture.whenStable(); // the first render is what wires the inputs to their form controls
  const input = (fixture.nativeElement as HTMLElement).querySelector<
    HTMLInputElement | HTMLTextAreaElement
  >(`[formcontrolname="${name}"]`)!;
  input.value = value;
  input.dispatchEvent(new Event('input'));
  await fixture.whenStable();
}

describe('TicketForm', () => {
  it('suggests knowledge base articles while the title is being typed', async () => {
    const { fixture, http, el } = setup();
    await type(fixture, 'title', 'VPN keeps dropping');
    await afterDebounce();
    const req = await respond(http, '/api/articles/suggest', [
      makeSummary({ id: 1, title: 'Fix a VPN that keeps disconnecting' }),
    ]);
    await fixture.whenStable();

    expect(req.request.params.get('q')).toBe('VPN keeps dropping');
    expect(el.querySelector('app-article-suggestions')?.textContent).toContain(
      'Fix a VPN that keeps disconnecting',
    );
  });

  it('does not get in the way of filing the ticket', async () => {
    const { fixture, http, el, navigate } = setup();
    await type(fixture, 'title', 'VPN keeps dropping');
    await type(fixture, 'description', 'Every ten minutes.');
    el.querySelector<HTMLButtonElement>('button[type=submit]')!.click();

    const req = await respond(http, '/api/tickets', makeTicket({ id: 12 }));
    expect(req.request.body).toMatchObject({
      title: 'VPN keeps dropping',
      description: 'Every ten minutes.',
    });
    await fixture.whenStable();
    expect(navigate).toHaveBeenCalledWith(['/tickets', 12]);
  });

  it('shows nothing until the title is long enough to search for', async () => {
    const { fixture, http, el } = setup();
    await type(fixture, 'title', 'vpn');
    await afterDebounce();
    http.expectNone((r) => r.url === '/api/articles/suggest');
    expect(el.querySelector('app-article-suggestions mat-card')).toBeNull();
  });
});
