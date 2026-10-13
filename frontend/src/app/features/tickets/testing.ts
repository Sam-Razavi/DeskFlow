import { signal } from '@angular/core';
import { HttpTestingController } from '@angular/common/http/testing';
import { Role, User } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { Ticket } from '../../core/tickets/ticket.models';

export const makeUser = (role: Role): User => ({
  id: role === 'requester' ? 1 : 2,
  email: `${role}@deskflow.dev`,
  full_name: role === 'requester' ? 'Grace User' : 'Alan Agent',
  role,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
});

export const authStub = (role: Role) => ({
  provide: AuthService,
  useValue: {
    user: signal(makeUser(role)),
    isStaff: () => role !== 'requester',
    hasRole: (...roles: Role[]) => roles.includes(role),
  },
});

export const makeTicket = (overrides: Partial<Ticket> = {}): Ticket => ({
  id: 7,
  title: 'Laptop will not boot',
  description: 'Black screen after the logo.',
  status: 'in_progress',
  priority: 'p2',
  category: 'hardware',
  requester: { id: 1, full_name: 'Grace User' },
  assignee: null,
  created_at: '2026-09-01T09:00:00Z',
  updated_at: '2026-09-01T09:00:00Z',
  resolved_at: null,
  ...overrides,
});

/** Component code awaits between requests, so poll until the expected one has been issued. */
export async function respond(
  http: HttpTestingController,
  url: string,
  body: object | null,
  options?: { status: number; statusText: string },
) {
  for (let i = 0; i < 25; i++) {
    const [req] = http.match((r) => r.url === url);
    if (req) {
      req.flush(body, options);
      return req;
    }
    await new Promise((resolve) => setTimeout(resolve));
  }
  throw new Error(`No request to ${url} was made`);
}
