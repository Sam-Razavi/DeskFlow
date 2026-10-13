import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { makeArticle, respond } from '../tickets/testing';
import { KbForm } from './kb-form';

function setup(id?: string) {
  TestBed.configureTestingModule({
    imports: [KbForm],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  });
  const fixture = TestBed.createComponent(KbForm);
  if (id) fixture.componentRef.setInput('id', id);
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  return {
    fixture,
    navigate,
    http: TestBed.inject(HttpTestingController),
    el: fixture.nativeElement as HTMLElement,
  };
}

const field = (el: HTMLElement, name: string) =>
  el.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[formcontrolname="${name}"]`)!;
const submit = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('button[type=submit]')!;

async function fill(fixture: ReturnType<typeof setup>['fixture'], values: Record<string, string>) {
  await fixture.whenStable(); // the first render is what wires the inputs to their form controls
  const el = fixture.nativeElement as HTMLElement;
  for (const [name, value] of Object.entries(values)) {
    field(el, name).value = value;
    field(el, name).dispatchEvent(new Event('input'));
  }
  await fixture.whenStable();
}

describe('KbForm', () => {
  it('needs a title and some text before it can be saved', async () => {
    const { fixture, el } = setup();
    await fixture.whenStable();
    expect(submit(el).disabled).toBe(true);

    await fill(fixture, { title: 'ab', body: 'Some text' });
    expect(submit(el).disabled).toBe(true); // title too short
    await fill(fixture, { title: 'Reset a password' });
    expect(submit(el).disabled).toBe(false);
  });

  it('previews the Markdown as you type', async () => {
    const { fixture, el } = setup();
    await fill(fixture, { body: '## Steps\n\n1. First\n2. Second' });

    const preview = el.querySelector('.editor__preview .markdown')!;
    expect(preview.querySelector('h2')?.textContent).toBe('Steps');
    expect(preview.querySelectorAll('li').length).toBe(2);

    await fill(fixture, { body: '' });
    expect(el.querySelector('.editor__preview .markdown')).toBeNull();
    expect(el.querySelector('.editor__empty')).not.toBeNull();
  });

  it('keeps hostile text out of the preview too', async () => {
    const { fixture, el } = setup();
    await fill(fixture, {
      body: 'Hi <script>window.__pwned=1</script><img src=x onerror=alert(1)>',
    });
    const preview = el.querySelector('.editor__preview')!;
    expect(preview.querySelector('script')).toBeNull();
    expect(preview.querySelector('[onerror]')).toBeNull();
  });

  it('saves a new article as a draft and opens it', async () => {
    const { fixture, el, http, navigate } = setup();
    await fill(fixture, { title: 'Reset a password', body: '## Steps' });
    submit(el).click();

    const req = await respond(http, '/api/articles', makeArticle({ id: 42, status: 'draft' }));
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      title: 'Reset a password',
      category: 'other',
      body: '## Steps',
    });
    await fixture.whenStable();
    expect(navigate).toHaveBeenCalledWith(['/kb', 42]);
  });

  it('loads an existing article for editing and saves the changes', async () => {
    const { fixture, el, http, navigate } = setup('3');
    await respond(http, '/api/articles/3', makeArticle({ title: 'Old title', body: 'Old body' }));
    await fixture.whenStable();
    expect(el.querySelector('h1')?.textContent).toContain('Edit article');
    expect(field(el, 'title').value).toBe('Old title');
    expect(field(el, 'body').value).toBe('Old body');

    await fill(fixture, { title: 'New title' });
    submit(el).click();
    const req = await respond(http, '/api/articles/3', makeArticle());
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ title: 'New title', category: 'access', body: 'Old body' });
    await fixture.whenStable();
    expect(navigate).toHaveBeenCalledWith(['/kb', 3]);
  });

  it('explains a failed save and lets you retry', async () => {
    const { fixture, el, http, navigate } = setup();
    await fill(fixture, { title: 'Reset a password', body: 'Text' });
    submit(el).click();
    await respond(http, '/api/articles', null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();

    expect(el.querySelector('[role=alert]')?.textContent).toContain('Could not save');
    expect(navigate).not.toHaveBeenCalled();
    expect(submit(el).disabled).toBe(false);
  });
});
