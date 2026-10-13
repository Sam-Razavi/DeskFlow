import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { FormBuilder, FormGroupDirective, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { User } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import {
  AuditEntry,
  CATEGORY_LABELS,
  describeDeadline,
  nextStatuses,
  PRIORITY_LABELS,
  Priority,
  SlaState,
  STATUS_LABELS,
  Ticket,
  TicketComment,
  TicketStatus,
  transitionLabel,
} from '../../core/tickets/ticket.models';
import { TicketService } from '../../core/tickets/ticket.service';
import { UserService } from '../../core/users/user.service';
import { SlaBadge } from './sla-badge';
import { Badge } from './status-badge';

const UNASSIGNED = 0;

@Component({
  selector: 'app-ticket-detail',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    Badge,
    SlaBadge,
  ],
  templateUrl: './ticket-detail.html',
  styleUrl: './ticket-detail.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketDetail {
  /** Bound from the `:id` route param (withComponentInputBinding). */
  readonly id = input.required<string>();

  private readonly tickets = inject(TicketService);
  private readonly users = inject(UserService);
  protected readonly auth = inject(AuthService);

  protected readonly ticket = signal<Ticket | null>(null);
  protected readonly comments = signal<TicketComment[]>([]);
  protected readonly history = signal<AuditEntry[]>([]);
  protected readonly agents = signal<User[]>([]);
  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly categoryLabels = CATEGORY_LABELS;
  protected readonly unassigned = UNASSIGNED;
  protected readonly transitionLabel = transitionLabel;

  protected readonly actions = computed(() => {
    const t = this.ticket();
    const user = this.auth.user();
    return t && user ? nextStatuses(t.status, user.role) : [];
  });
  protected readonly isClosed = computed(() => this.ticket()?.status === 'closed');

  // Ticks so the "due in …" text stays current while the page is open.
  private readonly now = signal(new Date());

  /** SLA details for staff; requesters don't see internal service-level measures. */
  protected readonly slaPanel = computed(() => {
    const t = this.ticket();
    if (!t || !this.auth.isStaff()) return null;
    const now = this.now();
    const when = (iso: string) => describeDeadline(new Date(iso), now);
    const paused = t.sla_paused_at !== null;
    const done = t.status === 'resolved' || t.status === 'closed';

    const response: { state: SlaState; text: string } = {
      state: t.response_sla,
      text: t.first_response_at
        ? 'Replied ' + this.shortDate(t.first_response_at)
        : done
          ? 'No reply was needed'
          : paused
            ? 'Clock paused while pending'
            : when(t.response_due_at),
    };
    const resolution: { state: SlaState; text: string } = {
      state: t.resolution_sla,
      text: t.resolved_at
        ? 'Resolved ' + this.shortDate(t.resolved_at)
        : paused
          ? 'Clock paused while pending'
          : when(t.resolution_due_at),
    };
    return { response, resolution };
  });

  private readonly replyForm = viewChild(FormGroupDirective);

  protected readonly commentForm = inject(FormBuilder).nonNullable.group({
    body: ['', [Validators.required, Validators.maxLength(10_000)]],
    internal: [false],
  });

  constructor() {
    const timer = setInterval(() => this.now.set(new Date()), 30_000);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
    effect(() => {
      const id = Number(this.id());
      untracked(() => void this.load(id));
    });
  }

  protected async changeStatus(status: TicketStatus): Promise<void> {
    await this.mutate(() => this.tickets.changeStatus(this.requireId(), status));
  }

  protected async assign(assigneeId: number): Promise<void> {
    await this.mutate(() =>
      this.tickets.assign(this.requireId(), assigneeId === UNASSIGNED ? null : assigneeId),
    );
  }

  protected async postComment(): Promise<void> {
    if (this.commentForm.invalid || this.busy()) return;
    const { body, internal } = this.commentForm.getRawValue();
    this.busy.set(true);
    this.error.set(null);
    try {
      await firstValueFrom(this.tickets.addComment(this.requireId(), body.trim(), internal));
      // resetForm (not reset) also clears the directive's "submitted" flag, which otherwise
      // leaves the emptied textarea showing its required-field error.
      this.replyForm()?.resetForm({ body: '', internal: false });
      await this.refreshActivity();
    } catch {
      this.error.set('Could not post the comment.');
    } finally {
      this.busy.set(false);
    }
  }

  protected describe(entry: AuditEntry): string {
    if (entry.action === 'created') return 'created the ticket';
    if (entry.action === 'sla_breached' || entry.action === 'sla_at_risk') {
      const verb = entry.action === 'sla_breached' ? 'breached' : 'at risk';
      return `SLA ${verb} (${String(entry.changes['kind'])})`;
    }
    if (entry.action === 'commented') {
      return entry.changes['is_internal'] ? 'added an internal note' : 'added a comment';
    }
    return Object.entries(entry.changes)
      .map(([field, value]) => this.formatChange(field, value))
      .join('; ');
  }

  private formatChange(field: string, value: unknown): string {
    const [from, to] = Array.isArray(value) ? value : [null, value];
    const label = field === 'assignee_id' ? 'assignee' : field.replace(/_/g, ' ');
    return `${label}: ${this.formatValue(field, from)} → ${this.formatValue(field, to)}`;
  }

  private formatValue(field: string, value: unknown): string {
    if (value === null || value === undefined) return field === 'assignee_id' ? 'unassigned' : '—';
    if (field === 'status') return STATUS_LABELS[value as TicketStatus] ?? String(value);
    if (field === 'priority') return PRIORITY_LABELS[value as Priority] ?? String(value);
    if (field === 'assignee_id') {
      return this.agents().find((a) => a.id === value)?.full_name ?? `user #${String(value)}`;
    }
    return String(value);
  }

  private shortDate(iso: string): string {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  private requireId(): number {
    return Number(this.id());
  }

  /** Runs an update that returns the new ticket, then refreshes the activity feeds. */
  private async mutate(call: () => ReturnType<TicketService['get']>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.ticket.set(await firstValueFrom(call()));
      await this.refreshActivity();
    } catch (err) {
      const detail = (err as { error?: { detail?: unknown } }).error?.detail;
      this.error.set(typeof detail === 'string' ? detail : 'That change could not be saved.');
    } finally {
      this.busy.set(false);
    }
  }

  private fetchActivity(id: number) {
    const staff = this.auth.isStaff();
    return Promise.all([
      firstValueFrom(this.tickets.comments(id)),
      staff ? firstValueFrom(this.tickets.history(id)) : Promise.resolve([] as AuditEntry[]),
    ]);
  }

  private async refreshActivity(): Promise<void> {
    const [comments, history] = await this.fetchActivity(this.requireId());
    this.comments.set(comments);
    this.history.set(history);
  }

  private async load(id: number): Promise<void> {
    this.loading.set(true);
    this.notFound.set(false);

    // Everything is requested at once. Only the ticket itself decides "not found"; the extras
    // are best-effort, and the catch stops a failed one from becoming an unhandled rejection.
    const ticket = firstValueFrom(this.tickets.get(id));
    const activity = this.fetchActivity(id).catch(() => null);
    const people =
      this.auth.isStaff() && this.agents().length === 0
        ? firstValueFrom(this.users.list()).catch(() => null)
        : Promise.resolve(null);

    try {
      this.ticket.set(await ticket);
    } catch {
      this.ticket.set(null);
      this.notFound.set(true);
      this.loading.set(false);
      return;
    }

    const [loaded, users] = await Promise.all([activity, people]);
    if (loaded) {
      this.comments.set(loaded[0]);
      this.history.set(loaded[1]);
    }
    if (users) this.agents.set(users.filter((u) => u.role !== 'requester' && u.is_active));
    this.loading.set(false);
  }
}
