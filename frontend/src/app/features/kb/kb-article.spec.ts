import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { Role } from '../../core/auth/auth.models';
import { Article } from '../../core/kb/article.models';
import { authStub, makeArticle, respond } from '../tickets/testing';
import { KbArticle } from './kb-article';

const history = [
  {
    id: 1,
    actor: { id: 2, full_name: 'Alan Agent' },
    entity_type: 'article',
    entity_id: 3,
    action: 'created',
    changes: {},
    created_at: '2026-10-05T09:00:00Z',
  },
  {
    id: 2,
    actor: { id: 2, full_name: 'Alan Agent' },
    entity_type: 'article',
    entity_id: 3,
    action: 'updated',
    changes: { title: ['Old', 'New'], body_changed: true },
    created_at: '2026-10-05T10:00:00Z',
  },
  {
    id: 3,
    actor: { id: 2, full_name: 'Alan Agent' },
    entity_type: 'article',
    entity_id: 3,
    action: 'published',
    changes: { status: ['draft', 'published'] },
    created_at: '2026-10-06T09:00:00Z',
  },
];

async function setup(role: Role, article: Article = makeArticle()) {
  TestBed.configureTestingModule({
    imports: [KbArticle],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), authStub(role)],
  });
  const fixture = TestBed.createComponent(KbArticle);
  const http = TestBed.inject(HttpTestingController);
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  fixture.componentRef.setInput('id', String(article.id));
  await respond(http, `/api/articles/${article.id}`, article);
  if (role !== 'requester') await respond(http, `/api/articles/${article.id}/history`, history);
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
  return { fixture, http, navigate, el: fixture.nativeElement as HTMLElement };
}

const button = (el: HTMLElement, text: string) =>
  [...el.querySelectorAll('button')].find((b) => b.textContent?.includes(text));

describe('KbArticle', () => {
  it('shows the article with its Markdown rendered', async () => {
    const { el } = await setup('requester');
    expect(el.querySelector('h1')?.textContent).toContain('How to reset your password');
    const body = el.querySelector('.markdown')!;
    expect(body.querySelector('h2')?.textContent).toBe('Steps');
    expect(body.querySelectorAll('ol li').length).toBe(2);
    expect(body.querySelector('strong')?.textContent).toBe('Forgot password');
    expect(el.textContent).toContain('Alan Agent');
  });

  it('cannot be turned against its reader: scripts, handlers and javascript: links are removed', async () => {
    const hostile = [
      'Before <script>window.__pwned = true</script> after',
      '<img src="x" onerror="window.__pwned = true">',
      '<a href="javascript:window.__pwned = true">click me</a>',
      '[markdown link](javascript:window.__pwned=true)',
      '<iframe src="https://evil.example"></iframe>',
      '<div onclick="window.__pwned = true">div</div>',
      '<style>body { display: none }</style>',
    ].join('\n\n');
    const { el } = await setup('requester', makeArticle({ body: hostile }));
    const body = el.querySelector('.markdown')!;

    expect(body.querySelector('script')).toBeNull();
    expect(body.querySelector('iframe')).toBeNull();
    expect(body.querySelector('style')).toBeNull();
    for (const node of body.querySelectorAll('*')) {
      const attrs = [...node.attributes].map((a) => a.name);
      expect(attrs.filter((n) => n.startsWith('on'))).toEqual([]);
      expect(node.getAttribute('href') ?? '').not.toMatch(/^\s*javascript:/i);
      expect(node.getAttribute('src') ?? '').not.toMatch(/^\s*javascript:/i);
    }
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
    // The harmless text around the attack is still there.
    expect(body.textContent).toContain('Before');
    expect(body.textContent).toContain('after');
  });

  it('shows requesters no editing tools or history', async () => {
    const { el } = await setup('requester');
    expect(el.querySelector('aside')).toBeNull();
    expect(el.textContent).not.toContain('History');
    expect(button(el, 'Publish')).toBeUndefined();
  });

  it('gives staff edit, unpublish and a readable history', async () => {
    const { el } = await setup('agent');
    expect(el.textContent).toContain('Edit');
    expect(button(el, 'Move back to draft')).toBeDefined();
    const text = el.querySelector('.history')!.textContent;
    expect(text).toContain('created the draft');
    expect(text).toContain('changed the title, edited the text');
    expect(text).toContain('published the article');
  });

  it('warns that a draft is hidden, and lets staff publish it', async () => {
    const { fixture, http, el } = await setup(
      'agent',
      makeArticle({ status: 'draft', published_at: null }),
    );
    expect(el.querySelector('.draft-banner')?.textContent).toContain('Only staff can see it');

    button(el, 'Publish')!.click();
    const req = await respond(http, '/api/articles/3/publish', makeArticle());
    expect(req.request.method).toBe('POST');
    await respond(http, '/api/articles/3/history', history);
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
    expect(el.querySelector('.draft-banner')).toBeNull();
    expect(button(el, 'Move back to draft')).toBeDefined();
  });

  it('lets staff delete a draft, after a confirmation', async () => {
    const { fixture, http, navigate, el } = await setup(
      'agent',
      makeArticle({ status: 'draft', published_at: null }),
    );
    button(el, 'Delete')!.click();
    await fixture.whenStable();
    expect(button(el, 'Confirm: delete for good')).toBeDefined();
    http.expectNone('/api/articles/3');

    button(el, 'Confirm: delete for good')!.click();
    const req = await respond(http, '/api/articles/3', null);
    expect(req.request.method).toBe('DELETE');
    await new Promise((resolve) => setTimeout(resolve));
    expect(navigate).toHaveBeenCalledWith(['/kb']);
  });

  it('lets you back out of deleting', async () => {
    const { fixture, http, el } = await setup(
      'agent',
      makeArticle({ status: 'draft', published_at: null }),
    );
    button(el, 'Delete')!.click();
    await fixture.whenStable();
    button(el, 'Keep it')!.click();
    await fixture.whenStable();
    expect(button(el, 'Confirm: delete for good')).toBeUndefined();
    http.expectNone('/api/articles/3');
  });

  it('only offers deleting a published article to admins', async () => {
    const agent = await setup('agent');
    expect(button(agent.el, 'Delete')).toBeUndefined();
    TestBed.resetTestingModule();

    const admin = await setup('admin');
    expect(button(admin.el, 'Delete')).toBeDefined();
  });

  it('shows the server message when a change is refused', async () => {
    const { fixture, http, el } = await setup('agent');
    button(el, 'Move back to draft')!.click();
    await respond(
      http,
      '/api/articles/3/unpublish',
      { detail: 'Article is already draft' },
      { status: 409, statusText: 'Conflict' },
    );
    await fixture.whenStable();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('already draft');
  });

  it('reports an article that does not exist or is not visible', async () => {
    TestBed.configureTestingModule({
      imports: [KbArticle],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        authStub('requester'),
      ],
    });
    const fixture = TestBed.createComponent(KbArticle);
    const http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('id', '99');
    await respond(http, '/api/articles/99', null, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain("doesn't exist");
  });
});
