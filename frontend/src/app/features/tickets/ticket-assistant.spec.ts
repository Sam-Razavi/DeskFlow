import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { respond } from './testing';
import { TicketAssistant } from './ticket-assistant';

async function setup() {
  TestBed.configureTestingModule({
    imports: [TicketAssistant],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  });
  const fixture = TestBed.createComponent(TicketAssistant);
  fixture.componentRef.setInput('ticketId', 7);
  const http = TestBed.inject(HttpTestingController);
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const button = () => el.querySelector('button') as HTMLButtonElement;
  const settle = async () => {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  };
  return { fixture, http, el, button, settle };
}

describe('TicketAssistant', () => {
  it('asks nothing until the button is pressed, because each run costs money', async () => {
    const { http } = await setup();
    http.expectNone('/api/tickets/7/assistant');
  });

  it('shows the steps as formatted text with links to the articles used', async () => {
    const { http, el, button, settle } = await setup();
    button().click();
    await respond(http, '/api/tickets/7/assistant', {
      answer: '1. **Restart** the client.',
      sources: [{ id: 3, title: 'Fixing a VPN' }],
      reason: null,
    });
    await settle();
    expect(el.querySelector('.answer strong')?.textContent).toBe('Restart');
    const link = el.querySelector('.sources a') as HTMLAnchorElement;
    expect(link.textContent).toBe('Fixing a VPN');
    expect(link.getAttribute('href')).toBe('/kb/3');
    expect(button().textContent).toContain('Ask again');
  });

  it('does not run script that arrives inside an answer', async () => {
    const { http, el, button, settle } = await setup();
    button().click();
    await respond(http, '/api/tickets/7/assistant', {
      answer: 'Hi <img src=x onerror="alert(1)"> <script>alert(2)</script>',
      sources: [{ id: 3, title: 'A' }],
      reason: null,
    });
    await settle();
    expect(el.querySelector('.answer script')).toBeNull();
    expect(el.querySelector('.answer [onerror]')).toBeNull();
  });

  it('explains the two ways there can be no answer', async () => {
    const { http, el, button, settle } = await setup();
    button().click();
    await respond(http, '/api/tickets/7/assistant', {
      answer: null,
      sources: [],
      reason: 'no_articles',
    });
    await settle();
    expect(el.textContent).toContain('No published knowledge-base article matches');

    button().click();
    await respond(http, '/api/tickets/7/assistant', {
      answer: null,
      sources: [],
      reason: 'not_covered',
    });
    await settle();
    expect(el.textContent).toContain('do not cover this problem');
    expect(el.textContent).not.toContain('No published knowledge-base article matches');
  });

  it('disables the button while waiting so it cannot be double-clicked', async () => {
    const { http, button, fixture, settle } = await setup();
    button().click();
    await fixture.whenStable();
    expect(button().disabled).toBe(true);
    await respond(http, '/api/tickets/7/assistant', {
      answer: null,
      sources: [],
      reason: 'no_articles',
    });
    await settle();
    expect(button().disabled).toBe(false);
    expect(http.match('/api/tickets/7/assistant').length).toBe(0);
  });

  it.each([
    [503, undefined, 'not been set up'],
    [429, { detail: 'Assistant limit reached. Try again in 12 minutes.' }, 'in 12 minutes'],
    [502, undefined, 'could not answer right now'],
  ])('reports a %s plainly', async (status, body, text) => {
    const { http, el, button, settle } = await setup();
    button().click();
    await respond(http, '/api/tickets/7/assistant', body ?? {}, { status, statusText: 'x' });
    await settle();
    expect(el.querySelector('[role=alert]')?.textContent).toContain(text);
    expect(button().disabled).toBe(false);
  });

  it('clears an old answer when a retry fails, rather than leaving a stale one up', async () => {
    const { http, el, button, settle } = await setup();
    button().click();
    await respond(http, '/api/tickets/7/assistant', {
      answer: 'Old',
      sources: [{ id: 1, title: 'A' }],
      reason: null,
    });
    await settle();
    button().click();
    await respond(http, '/api/tickets/7/assistant', {}, { status: 502, statusText: 'x' });
    await settle();
    expect(el.querySelector('.answer')).toBeNull();
  });
});
