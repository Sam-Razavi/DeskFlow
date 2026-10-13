import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

const withToken = (req: HttpRequest<unknown>, token: string | null) =>
  token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

const isAuthEndpoint = (url: string) =>
  url.includes('/api/auth/login') || url.includes('/api/auth/refresh');

/** Attaches the access token and transparently refreshes it once on a 401. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  if (isAuthEndpoint(req.url)) return next(req);

  return next(withToken(req, auth.accessToken)).pipe(
    catchError((err: unknown) => {
      if (!(err instanceof HttpErrorResponse) || err.status !== 401) return throwError(() => err);
      return auth.refresh().pipe(
        switchMap((tokens) => next(withToken(req, tokens.access_token))),
        catchError((refreshErr: unknown) => {
          auth.logout();
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};
