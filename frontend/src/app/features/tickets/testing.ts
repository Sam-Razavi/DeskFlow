import { signal } from '@angular/core';
import { HttpTestingController } from '@angular/common/http/testing';
import { Role, User } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { Asset } from '../../core/assets/asset.models';
import { Article, ArticleSummary } from '../../core/kb/article.models';
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
  first_response_at: null,
  response_due_at: '2026-09-01T13:00:00Z',
  resolution_due_at: '2026-09-01T17:00:00Z',
  sla_paused_at: null,
  response_sla: 'ok',
  resolution_sla: 'ok',
  sla_state: 'ok',
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

export const makeAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 11,
  asset_tag: 'DF-00011',
  type: 'laptop',
  manufacturer: 'Dell',
  model: 'Latitude 7440',
  serial_number: 'SN-1001',
  status: 'in_stock',
  assigned_to: null,
  location: 'HQ stockroom',
  purchase_date: '2026-01-15',
  warranty_expires_on: '2029-01-15',
  notes: null,
  created_at: '2026-01-15T09:00:00Z',
  updated_at: '2026-01-15T09:00:00Z',
  warranty_state: 'active',
  ...overrides,
});

export const makeSummary = (overrides: Partial<ArticleSummary> = {}): ArticleSummary => ({
  id: 3,
  title: 'How to reset your password',
  category: 'access',
  status: 'published',
  author: { id: 2, full_name: 'Alan Agent' },
  published_at: '2026-10-06T09:00:00Z',
  updated_at: '2026-10-06T09:00:00Z',
  snippet: 'Open the portal and choose Forgot password.',
  ...overrides,
});

export const makeArticle = (overrides: Partial<Article> = {}): Article => ({
  id: 3,
  title: 'How to reset your password',
  body: '## Steps\n\n1. Open the portal\n2. Choose **Forgot password**',
  category: 'access',
  status: 'published',
  author: { id: 2, full_name: 'Alan Agent' },
  published_at: '2026-10-06T09:00:00Z',
  created_at: '2026-10-05T09:00:00Z',
  updated_at: '2026-10-06T09:00:00Z',
  ...overrides,
});

/** Waits long enough for a debounced input to fire its request. */
export const afterDebounce = (ms = 450) => new Promise((resolve) => setTimeout(resolve, ms));
