import { Routes } from '@angular/router';
import { authGuard, guestGuard, roleGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/login/login').then((m) => m.Login),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/shell').then((m) => m.Shell),
    children: [
      {
        path: '',
        loadComponent: () => import('./features/dashboard/dashboard').then((m) => m.Dashboard),
      },
      {
        path: 'tickets',
        children: [
          {
            path: '',
            loadComponent: () => import('./features/tickets/ticket-list').then((m) => m.TicketList),
          },
          {
            path: 'new',
            loadComponent: () => import('./features/tickets/ticket-form').then((m) => m.TicketForm),
          },
          {
            path: ':id',
            loadComponent: () =>
              import('./features/tickets/ticket-detail').then((m) => m.TicketDetail),
          },
        ],
      },
      {
        path: 'kb',
        children: [
          {
            path: '',
            loadComponent: () => import('./features/kb/kb-list').then((m) => m.KbList),
          },
          {
            path: 'new',
            canActivate: [roleGuard('agent', 'admin')],
            loadComponent: () => import('./features/kb/kb-form').then((m) => m.KbForm),
          },
          {
            path: ':id/edit',
            canActivate: [roleGuard('agent', 'admin')],
            loadComponent: () => import('./features/kb/kb-form').then((m) => m.KbForm),
          },
          {
            path: ':id',
            loadComponent: () => import('./features/kb/kb-article').then((m) => m.KbArticle),
          },
        ],
      },
      {
        path: 'assets',
        children: [
          {
            path: '',
            loadComponent: () => import('./features/assets/asset-list').then((m) => m.AssetList),
          },
          {
            path: 'new',
            canActivate: [roleGuard('agent', 'admin')],
            loadComponent: () => import('./features/assets/asset-form').then((m) => m.AssetForm),
          },
          {
            path: ':id/edit',
            canActivate: [roleGuard('agent', 'admin')],
            loadComponent: () => import('./features/assets/asset-form').then((m) => m.AssetForm),
          },
          {
            path: ':id',
            loadComponent: () =>
              import('./features/assets/asset-detail').then((m) => m.AssetDetail),
          },
        ],
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
