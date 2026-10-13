import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { authInterceptor } from './auth.interceptor';

describe('authInterceptor', () => {
  let client: HttpClient;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('deskflow.access', 'old-access');
    localStorage.setItem('deskflow.refresh', 'refresh');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([{ path: '**', children: [] }]),
      ],
    });
    client = TestBed.inject(HttpClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('attaches the bearer token', () => {
    client.get('/api/users').subscribe();
    const req = http.expectOne('/api/users');
    expect(req.request.headers.get('Authorization')).toBe('Bearer old-access');
    req.flush([]);
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    const result = firstValueFrom(client.get<string[]>('/api/users'));

    http.expectOne('/api/users').flush(null, { status: 401, statusText: 'Unauthorized' });
    http
      .expectOne('/api/auth/refresh')
      .flush({ access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' });
    const retry = http.expectOne('/api/users');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer new-access');
    retry.flush(['ok']);

    expect(await result).toEqual(['ok']);
    expect(localStorage.getItem('deskflow.refresh')).toBe('new-refresh');
  });

  it('logs out when the refresh fails', async () => {
    const result = firstValueFrom(client.get('/api/users'));

    http.expectOne('/api/users').flush(null, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/auth/refresh').flush(null, { status: 401, statusText: 'Unauthorized' });

    await expect(result).rejects.toBeTruthy();
    expect(localStorage.getItem('deskflow.access')).toBeNull();
  });
});
