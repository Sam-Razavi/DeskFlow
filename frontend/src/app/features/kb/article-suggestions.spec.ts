import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterDebounce, makeSummary, respond } from '../tickets/testing';
import { ArticleSuggestions } from './article-suggestions';

function setup() {
  TestBed.configureTestingModule({
    imports: [ArticleSuggestions],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  });
  const fixture = TestBed.createComponent(ArticleSuggestions);
  return {
    fixture,
    http: TestBed.inject(HttpTestingController),
    el: fixture.nativeElement as HTMLElement,
    type: async (text: string) => {
      fixture.componentRef.setInput('query', text);
      await fixture.whenStable();
    },
  };
}

describe('ArticleSuggestions', () => {
  it('suggests articles for what is being typed, in a new tab', async () => {
    const { fixture, http, el, type } = setup();
    await type('VPN keeps dropping');
    await afterDebounce();
    const req = await respond(http, '/api/articles/suggest', [
      makeSummary({ id: 1, title: 'Fix a VPN that keeps disconnecting' }),
    ]);
    await fixture.whenStable();

    expect(req.request.params.get('q')).toBe('VPN keeps dropping');
    expect(el.textContent).toContain('These articles might help');
    const link = el.querySelector('a')!;
    expect(link.textContent).toContain('Fix a VPN that keeps disconnecting');
    expect(link.getAttribute('href')).toBe('/kb/1');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
  });

  it('waits for a pause in typing and only asks about the latest text', async () => {
    const { http, type } = setup();
    await type('printer jam');
    await type('printer toner');
    await afterDebounce();

    const requests = http.match((r) => r.url === '/api/articles/suggest');
    expect(requests.length).toBe(1);
    expect(requests[0].request.params.get('q')).toBe('printer toner');
  });

  it('does not ask until there is enough text to be meaningful', async () => {
    const { http, el, type } = setup();
    await type('vpn');
    await afterDebounce();
    http.expectNone((r) => r.url === '/api/articles/suggest');
    expect(el.querySelector('mat-card')).toBeNull();
  });

  it('shows nothing when there are no matches', async () => {
    const { fixture, http, el, type } = setup();
    await type('quantum entanglement');
    await afterDebounce();
    await respond(http, '/api/articles/suggest', []);
    await fixture.whenStable();
    expect(el.querySelector('mat-card')).toBeNull();
  });

  it('stays out of the way if the lookup fails', async () => {
    const { fixture, http, el, type } = setup();
    await type('vpn keeps dropping');
    await afterDebounce();
    await respond(http, '/api/articles/suggest', null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect(el.querySelector('mat-card')).toBeNull();
    expect(el.querySelector('[role=alert]')).toBeNull();
  });

  it('removes the suggestions again when the text is cleared', async () => {
    const { fixture, http, el, type } = setup();
    await type('vpn keeps dropping');
    await afterDebounce();
    await respond(http, '/api/articles/suggest', [makeSummary()]);
    await fixture.whenStable();
    expect(el.querySelector('mat-card')).not.toBeNull();

    await type('');
    await afterDebounce();
    await fixture.whenStable();
    expect(el.querySelector('mat-card')).toBeNull();
  });

  it('uses the heading and limit it is given', async () => {
    const { fixture, http, el } = setup();
    fixture.componentRef.setInput('query', 'wifi problems');
    fixture.componentRef.setInput('heading', 'Suggested articles');
    fixture.componentRef.setInput('limit', 2);
    await fixture.whenStable();
    await afterDebounce();
    const req = await respond(http, '/api/articles/suggest', [makeSummary()]);
    await fixture.whenStable();
    expect(req.request.params.get('limit')).toBe('2');
    expect(el.textContent).toContain('Suggested articles');
  });
});
