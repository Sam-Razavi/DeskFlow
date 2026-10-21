import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
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
import { RouterLink } from '@angular/router';
import { debounceTime, firstValueFrom } from 'rxjs';
import {
  describeChanges,
  humanize,
  recordGone,
  recordLabel,
  recordLink,
} from '../../core/audit/audit-format';
import { AuditFacets, AuditFilters } from '../../core/audit/audit.models';
import { AuditService } from '../../core/audit/audit.service';
import { User } from '../../core/auth/auth.models';
import { saveBlob } from '../../core/download';
import { AuditEntry } from '../../core/tickets/ticket.models';
import { UserService } from '../../core/users/user.service';

@Component({
  selector: 'app-audit-log',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatSelectModule,
    MatTableModule,
  ],
  templateUrl: './audit-log.html',
  styleUrl: './audit-log.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuditLog {
  private readonly audit = inject(AuditService);
  private readonly users = inject(UserService);

  protected readonly columns = ['when', 'who', 'action', 'record', 'details'];
  protected readonly humanize = humanize;
  protected readonly recordLink = recordLink;
  protected readonly recordLabel = recordLabel;
  protected readonly recordGone = recordGone;

  protected readonly rows = signal<AuditEntry[]>([]);
  protected readonly total = signal(0);
  protected readonly facets = signal<AuditFacets>({ entity_types: [], actions: [] });
  protected readonly people = signal<User[]>([]);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly exporting = signal(false);
  protected readonly exportFailed = signal(false);
  protected readonly pageSize = signal(50);
  protected readonly pageIndex = signal(0);

  protected readonly filters = new FormGroup({
    entityType: new FormControl<string | null>(null),
    action: new FormControl<string | null>(null),
    actorId: new FormControl<number | null>(null),
    entityId: new FormControl<number | null>(null),
    from: new FormControl('', { nonNullable: true }),
    to: new FormControl('', { nonNullable: true }),
  });

  private readonly nameById = computed(
    () => new Map(this.people().map((u) => [u.id, u.full_name])),
  );
  protected readonly nameOf = (id: number) => this.nameById().get(id);

  constructor() {
    this.filters.valueChanges
      .pipe(debounceTime(300), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        this.pageIndex.set(0);
        void this.reload();
      });
    // The dropdowns are a convenience: if either lookup fails the log is still fully usable.
    void firstValueFrom(this.audit.facets())
      .then((f) => this.facets.set(f))
      .catch(() => undefined);
    void firstValueFrom(this.users.list())
      .then((u) => this.people.set(u))
      .catch(() => undefined);
    void this.reload();
  }

  protected get hasFilters(): boolean {
    return Object.values(this.filters.getRawValue()).some((v) => v !== null && v !== '');
  }

  protected clearFilters(): void {
    this.filters.reset({
      entityType: null,
      action: null,
      actorId: null,
      entityId: null,
      from: '',
      to: '',
    });
  }

  protected onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    void this.reload();
  }

  protected summary(entry: AuditEntry): string {
    return describeChanges(entry, this.nameOf);
  }

  protected raw(entry: AuditEntry): string {
    return JSON.stringify(entry.changes, null, 2);
  }

  protected async exportCsv(): Promise<void> {
    this.exporting.set(true);
    this.exportFailed.set(false);
    try {
      const blob = await firstValueFrom(this.audit.exportCsv(this.currentFilters()));
      saveBlob(blob, `audit-log-${new Date().toISOString().slice(0, 10)}.csv`);
    } catch {
      this.exportFailed.set(true);
    } finally {
      this.exporting.set(false);
    }
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    try {
      const page = await firstValueFrom(
        this.audit.list({
          ...this.currentFilters(),
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

  private currentFilters(): AuditFilters {
    const v = this.filters.getRawValue();
    return {
      entityType: v.entityType ?? undefined,
      action: v.action ?? undefined,
      actorId: v.actorId ?? undefined,
      // A number input reports an empty box as null (or NaN once cleared); neither is a filter.
      entityId:
        typeof v.entityId === 'number' && !Number.isNaN(v.entityId) ? v.entityId : undefined,
      from: v.from || undefined,
      to: v.to || undefined,
    };
  }
}
