import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { debounceTime, firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import {
  CATEGORIES,
  Category,
  CATEGORY_LABELS,
  Priority,
  PRIORITIES,
  PRIORITY_LABELS,
  STATUS_LABELS,
  STATUSES,
  Ticket,
  TicketStatus,
} from '../../core/tickets/ticket.models';
import { TicketService } from '../../core/tickets/ticket.service';
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
  protected readonly columns = [
    'id',
    'title',
    'status',
    'priority',
    'requester',
    'assignee',
    'created',
  ];

  protected readonly rows = signal<Ticket[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly pageSize = signal(25);
  protected readonly pageIndex = signal(0);

  protected readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true }),
    status: new FormControl<TicketStatus | null>(null),
    priority: new FormControl<Priority | null>(null),
    category: new FormControl<Category | null>(null),
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

  protected onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    void this.reload();
  }

  protected clearFilters(): void {
    this.filters.reset({ q: '', status: null, priority: null, category: null });
  }

  protected get hasFilters(): boolean {
    const { q, status, priority, category } = this.filters.getRawValue();
    return !!(q || status || priority || category);
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    const { q, status, priority, category } = this.filters.getRawValue();
    try {
      const page = await firstValueFrom(
        this.tickets.list({
          q: q.trim() || undefined,
          status: status ?? undefined,
          priority: priority ?? undefined,
          category: category ?? undefined,
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
