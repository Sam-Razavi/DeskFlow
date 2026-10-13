import { HttpClient } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom, Observable, tap } from 'rxjs';
import { Role, TokenPair, User } from './auth.models';

const ACCESS_KEY = 'deskflow.access';
const REFRESH_KEY = 'deskflow.refresh';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly _user = signal<User | null>(null);
  readonly user = this._user.asReadonly();
  readonly isAuthenticated = computed(() => this._user() !== null);
  readonly isStaff = computed(() => this.hasRole('agent', 'admin'));

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  hasRole(...roles: Role[]): boolean {
    const user = this._user();
    return user !== null && roles.includes(user.role);
  }

  async login(email: string, password: string): Promise<void> {
    const body = new URLSearchParams({ username: email, password });
    const tokens = await firstValueFrom(
      this.http.post<TokenPair>('/api/auth/login', body.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }),
    );
    this.storeTokens(tokens);
    await this.loadCurrentUser();
  }

  /** Restores the session on app start; silently clears invalid tokens. */
  async restoreSession(): Promise<void> {
    if (!this.accessToken) return;
    try {
      await this.loadCurrentUser();
    } catch {
      this.clearSession();
    }
  }

  refresh(): Observable<TokenPair> {
    const refresh_token = localStorage.getItem(REFRESH_KEY) ?? '';
    return this.http
      .post<TokenPair>('/api/auth/refresh', { refresh_token })
      .pipe(tap((tokens) => this.storeTokens(tokens)));
  }

  logout(): void {
    this.clearSession();
    void this.router.navigate(['/login']);
  }

  private async loadCurrentUser(): Promise<void> {
    this._user.set(await firstValueFrom(this.http.get<User>('/api/auth/me')));
  }

  private storeTokens(tokens: TokenPair): void {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }

  private clearSession(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    this._user.set(null);
  }
}
