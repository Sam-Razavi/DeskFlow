import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { Role } from '../../core/auth/auth.models';
import { afterDebounce, authStub, makeSummary, respond } from '../tickets/testing';
import { KbList } from './kb-list';

const labels = (el: HTMLElement) =>
  [...el.querySelectorAll('mat-label')].map((l) => l.textContent?.trim());

function setup(role: Role) {
  TestBed.configureTestingModule({
    imports: [KbList],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(KbList);
  return {
    fixture,
    http: TestBed.inject(HttpTestingController),
    el: fixture.nativeElement as HTMLElement,
  };
}

describe('KbList', () => {
  it('lists articles with their category, author and a plain-text excerpt', async () => {
    const { fixture, http, el } = setup('requester');
    await respond(http, '/api/articles', {
      items: [
        makeSummary({ id: 1, title: 'Fix a VPN that keeps disconnecting', category: 'network' }),
        makeSummary({ id: 2, title: 'Add a network printer', category: 'hardware' }),
      ],
      total: 2,
    });
    await fixture.whenStable();

    const results = [...el.querySelectorAll('.result')];
    expect(results.length).toBe(2);
    expect(results[0].textContent).toContain('Fix a VPN that keeps disconnecting');
    expect(results[0].textContent).toContain('Network');
    expect(results[0].textContent).toContain('Alan Agent');
    expect(results[0].querySelector('a')!.getAttribute('href')).toBe('/kb/1');
  });

  it('highlights search matches with <mark>, and renders everything else as text', async () => {
    const { fixture, http, el } = setup('requester');
    await respond(http, '/api/articles', {
      items: [
        makeSummary({
          snippet: 'Restart the ⟦VPN⟧ client. <img src=x onerror=alert(1)> then retry.',
        }),
      ],
      total: 1,
    });
    await fixture.whenStable();

    const marks = [...el.querySelectorAll('.result__snippet mark')];
    expect(marks.map((m) => m.textContent)).toEqual(['VPN']);
    // Highlighting must not change the text: no stray gap before the full stop that follows a match.
    expect(el.querySelector('.result__snippet')!.textContent!.trim()).toBe(
      'Restart the VPN client. <img src=x onerror=alert(1)> then retry.',
    );
    // Markup inside a snippet is shown as literal text, never interpreted.
    expect(el.querySelector('.result__snippet img')).toBeNull();
    expect(el.querySelector('.result__snippet')!.textContent).toContain(
      '<img src=x onerror=alert(1)>',
    );
  });

  it('searches as you type, after a short pause', async () => {
    const { fixture, http, el } = setup('requester');
    await respond(http, '/api/articles', { items: [], total: 0 });
    await fixture.whenStable();

    const input = el.querySelector<HTMLInputElement>('input[formcontrolname="q"]')!;
    input.value = 'vpn';
    input.dispatchEvent(new Event('input'));
    await afterDebounce(350);
    const req = await respond(http, '/api/articles', { items: [makeSummary()], total: 1 });
    expect(req.request.params.get('q')).toBe('vpn');
    await fixture.whenStable();
    expect(el.querySelectorAll('.result').length).toBe(1);
  });

  it('quotes the search back when nothing matches and offers a way forward', async () => {
    const { fixture, http, el } = setup('requester');
    await respond(http, '/api/articles', { items: [], total: 0 });
    await fixture.whenStable();
    const input = el.querySelector<HTMLInputElement>('input[formcontrolname="q"]')!;
    input.value = 'xylophone';
    input.dispatchEvent(new Event('input'));
    await afterDebounce(350);
    await respond(http, '/api/articles', { items: [], total: 0 });
    await fixture.whenStable();

    expect(el.querySelector('.state')!.textContent).toContain('Nothing found for “xylophone”');
    expect(el.querySelector('.state a')!.getAttribute('href')).toBe('/tickets/new');
  });

  it('shows staff the status filter, drafts and the new-article button', async () => {
    const { fixture, http, el } = setup('agent');
    await respond(http, '/api/articles', {
      items: [makeSummary({ id: 9, title: 'Unfinished', status: 'draft', published_at: null })],
      total: 1,
    });
    await fixture.whenStable();

    expect(labels(el)).toContain('Status');
    expect(el.textContent).toContain('New article');
    expect(el.querySelector('.chip--draft')?.textContent).toContain('Draft');
  });

  it('keeps requesters to published articles, with no status filter or editing', async () => {
    const { fixture, http, el } = setup('requester');
    const req = await respond(http, '/api/articles', { items: [], total: 0 });
    await fixture.whenStable();

    expect(labels(el)).not.toContain('Status');
    expect(el.textContent).not.toContain('New article');
    expect(req.request.params.has('status')).toBe(false);
  });

  it('offers a retry when loading fails', async () => {
    const { fixture, http, el } = setup('agent');
    await respond(http, '/api/articles', null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Could not load articles');

    [...el.querySelectorAll('button')].find((b) => b.textContent?.includes('Retry'))!.click();
    await respond(http, '/api/articles', { items: [], total: 0 });
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')).toBeNull();
  });
});

describe('KbList deep links', () => {
  async function open(query: string) {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'kb', component: KbList }]),
        authStub('agent'),
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const navigation = RouterTestingHarness.create().then((h) =>
      h.navigateByUrl('/kb' + query, KbList),
    );
    const req = await respond(http, '/api/articles', { items: [], total: 0 });
    await navigation;
    return req.request.params;
  }

  it('applies filters from the query string', async () => {
    const params = await open('?q=vpn&category=network&status=draft');
    expect(params.get('q')).toBe('vpn');
    expect(params.get('category')).toBe('network');
    expect(params.get('status')).toBe('draft');
  });

  it('ignores category and status values that are not real options', async () => {
    const params = await open('?category=weather&status=hacked');
    expect(params.has('category')).toBe(false);
    expect(params.has('status')).toBe(false);
  });
});
