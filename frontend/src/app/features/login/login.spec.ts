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
});
