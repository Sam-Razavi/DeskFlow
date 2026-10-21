import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { Login } from './login';

describe('Login', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [Login],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
  });

  it('fills credentials from a demo account button', async () => {
    const fixture = TestBed.createComponent(Login);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;

    const demoButton = [...el.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Agent'),
    )!;
    demoButton.click();
    await fixture.whenStable();

    expect(el.querySelector<HTMLInputElement>('input[type=email]')!.value).toBe(
      'agent@deskflow.dev',
    );
  });

  it('says the demo data is reset daily', async () => {
    const fixture = TestBed.createComponent(Login);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.login__demo')?.textContent).toContain('Demo data resets daily');
  });

  it('shows an error on bad credentials', async () => {
    const fixture = TestBed.createComponent(Login);
    const http = TestBed.inject(HttpTestingController);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl');
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;

    const email = el.querySelector<HTMLInputElement>('input[type=email]')!;
    const password = el.querySelector<HTMLInputElement>('input[type=password]')!;
    email.value = 'user@deskflow.dev';
    email.dispatchEvent(new Event('input'));
    password.value = 'wrong';
    password.dispatchEvent(new Event('input'));
    el.querySelector('form')!.dispatchEvent(new Event('submit'));

    http.expectOne('/api/auth/login').flush(null, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();

    expect(el.querySelector('[role=alert]')?.textContent).toContain('Incorrect email or password');
    expect(navigate).not.toHaveBeenCalled();
  });

  async function failWith(status: number, body: object | null) {
    const fixture = TestBed.createComponent(Login);
    const http = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    for (const [name, value] of [
      ['email', 'user@deskflow.dev'],
      ['password', 'whatever'],
    ]) {
      const input = el.querySelector<HTMLInputElement>(`input[type=${name}]`)!;
      input.value = value;
      input.dispatchEvent(new Event('input'));
    }
    el.querySelector('form')!.dispatchEvent(new Event('submit'));
    http.expectOne('/api/auth/login').flush(body, { status, statusText: 'Error' });
    await fixture.whenStable();
    return el.querySelector('[role=alert]')?.textContent ?? '';
  }

  it('tells a locked-out user how long to wait, in the words the server gives', async () => {
    const message = await failWith(429, {
      detail: 'Too many failed sign-in attempts. Try again in 15 minutes.',
    });
    expect(message).toContain('Try again in 15 minutes');
  });

  it('still gives a sensible message if a 429 carries no detail', async () => {
    expect(await failWith(429, null)).toContain('Too many attempts');
  });

  it('keeps the generic message for unexpected failures', async () => {
    expect(await failWith(500, null)).toContain('Something went wrong');
  });
});
