import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { User } from './auth.models';
import { AuthService } from './auth.service';

const agent: User = {
  id: 1,
  email: 'agent@deskflow.dev',
  full_name: 'Alan Agent',
  role: 'agent',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

describe('AuthService', () => {
  let service: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    service = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('logs in with form-encoded credentials and loads the user', async () => {
    const done = service.login('agent@deskflow.dev', 'secret');

    const loginReq = http.expectOne('/api/auth/login');
    expect(loginReq.request.body).toBe('username=agent%40deskflow.dev&password=secret');
    loginReq.flush({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' });
    await Promise.resolve();
    http.expectOne('/api/auth/me').flush(agent);
    await done;

    expect(service.user()).toEqual(agent);
    expect(service.isStaff()).toBe(true);
    expect(service.accessToken).toBe('a');
  });

  it('clears invalid tokens when restoring a session fails', async () => {
    localStorage.setItem('deskflow.access', 'stale');
    const done = service.restoreSession();
    http.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    await done;

    expect(service.isAuthenticated()).toBe(false);
    expect(service.accessToken).toBeNull();
  });

  it('does not call the API when there is no stored token', async () => {
    await service.restoreSession();
    http.expectNone('/api/auth/me');
  });
});
