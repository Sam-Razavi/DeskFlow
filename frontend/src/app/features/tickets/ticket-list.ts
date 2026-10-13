import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { debounceTime, firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import {
  CATEGORIES,
  Assignment,
  Category,
  CATEGORY_LABELS,
  Priority,
  PRIORITIES,
  PRIORITY_LABELS,
  SlaFilter,
  STATUS_LABELS,
  STATUSES,
  Ticket,
  TicketStatus,
} from '../../core/tickets/ticket.models';
import { TicketService } from '../../core/tickets/ticket.service';
import { SlaBadge } from './sla-badge';
import { Badge } from './status-badge';

@Component({
  selector: 'app-ticket-list',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatSelectModule,
    MatTableModule,
    Badge,
    SlaBadge,
    DatePipe,
  ],
  templateUrl: './ticket-list.html',
  styleUrl: './ticket-list.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketList {
  private readonly tickets = inject(TicketService);
  protected readonly auth = inject(AuthService);

  protected readonly statuses = STATUSES;
  protected readonly priorities = PRIORITIES;
  protected readonly categories = CATEGORIES;
  protected readonly statusLabels = STATUS_LABELS;
  protected readonly priorityLabels = PRIORITY_LABELS;
  protected readonly categoryLabels = CATEGORY_LABELS;
  private readonly baseColumns = [
    'id',
    'title',
    'status',
    'priority',
    'requester',
    'assignee',
    'created',
  ];
  // SLA is an internal measure, so only staff get the column and its filters.
  protected readonly columns = computed(() => {
    const cols = [...this.baseColumns];
    if (this.auth.isStaff()) cols.splice(3, 0, 'sla');
    return cols;
  });

  protected readonly rows = signal<Ticket[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly pageSize = signal(25);
  protected readonly pageIndex = signal(0);

  // The dashboard deep-links here with ?sla=breached, ?assignment=mine, ?status=resolved, etc.
  private readonly params = inject(ActivatedRoute).snapshot.queryParamMap;

  protected readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true }),
    status: new FormControl<TicketStatus | null>(this.fromParam<TicketStatus>(STATUSES, 'status')),
    priority: new FormControl<Priority | null>(null),
    category: new FormControl<Category | null>(null),
    sla: new FormControl<SlaFilter | null>(
      this.fromParam<SlaFilter>(['breached', 'at_risk'], 'sla'),
    ),
    assignment: new FormControl<Assignment | null>(
      this.fromParam<Assignment>(['unassigned', 'mine'], 'assignment'),
    ),
  });

  constructor() {
    // Text search is debounced; the selects change rarely so debouncing them is harmless.
    this.filters.valueChanges
      .pipe(debounceTime(250), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        this.pageIndex.set(0);
        void this.reload();
      });
    void this.reload();
  }

  /** Only accept a query-param value that is a real option, so a hand-edited URL can't inject junk. */
  private fromParam<T extends string>(allowed: readonly T[], name: string): T | null {
    const value = this.params.get(name);
    return allowed.find((a) => a === value) ?? null;
  }

  protected onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    void this.reload();
  }

  protected clearFilters(): void {
    this.filters.reset({
      q: '',
      status: null,
      priority: null,
      category: null,
      sla: null,
      assignment: null,
    });
  }

  protected get hasFilters(): boolean {
    return Object.values(this.filters.getRawValue()).some(Boolean);
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    const { q, status, priority, category, sla, assignment } = this.filters.getRawValue();
    try {
      const page = await firstValueFrom(
        this.tickets.list({
          q: q.trim() || undefined,
          status: status ?? undefined,
          priority: priority ?? undefined,
          category: category ?? undefined,
          sla: sla ?? undefined,
          unassigned: assignment === 'unassigned',
          assigneeId: assignment === 'mine' ? this.auth.user()?.id : undefined,
          limit: this.pageSize(),
          offset: this.pageIndex() * this.pageSize(),
        }),
      );
      this.rows.set(page.items);
      this.total.set(page.total);
    } catch {
      this.failed.set(true);
    } finally {
      this.loading.set(false);
    }
  }
}
