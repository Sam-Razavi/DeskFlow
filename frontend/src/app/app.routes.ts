import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/auth/auth.guard';

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
    ],
  },
  { path: '**', redirectTo: '' },
];
