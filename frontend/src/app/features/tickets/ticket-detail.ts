import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
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
  nextStatuses,
  PRIORITY_LABELS,
  Priority,
  STATUS_LABELS,
  Ticket,
  TicketComment,
  TicketStatus,
  transitionLabel,
} from '../../core/tickets/ticket.models';
import { TicketService } from '../../core/tickets/ticket.service';
import { UserService } from '../../core/users/user.service';
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

  private readonly replyForm = viewChild(FormGroupDirective);

  protected readonly commentForm = inject(FormBuilder).nonNullable.group({
    body: ['', [Validators.required, Validators.maxLength(10_000)]],
    internal: [false],
  });

  constructor() {
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

  private async refreshActivity(): Promise<void> {
    const id = this.requireId();
    this.comments.set(await firstValueFrom(this.tickets.comments(id)));
    if (this.auth.isStaff()) this.history.set(await firstValueFrom(this.tickets.history(id)));
  }

  private async load(id: number): Promise<void> {
    this.loading.set(true);
    this.notFound.set(false);
    try {
      this.ticket.set(await firstValueFrom(this.tickets.get(id)));
      await this.refreshActivity();
      if (this.auth.isStaff() && this.agents().length === 0) {
        const all = await firstValueFrom(this.users.list());
        this.agents.set(all.filter((u) => u.role !== 'requester' && u.is_active));
      }
    } catch {
      this.ticket.set(null);
      this.notFound.set(true);
    } finally {
      this.loading.set(false);
    }
  }
}
