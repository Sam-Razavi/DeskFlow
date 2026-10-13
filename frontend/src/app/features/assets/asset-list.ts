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
import {
  Asset,
  ASSET_STATUS_LABELS,
  ASSET_STATUSES,
  ASSET_TYPE_LABELS,
  ASSET_TYPES,
  AssetStatus,
  AssetType,
  WarrantyFilter,
} from '../../core/assets/asset.models';
import { AssetService } from '../../core/assets/asset.service';
import { AuthService } from '../../core/auth/auth.service';
import { AssetStatusBadge, WarrantyBadge } from './asset-badges';

@Component({
  selector: 'app-asset-list',
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
    AssetStatusBadge,
    WarrantyBadge,
  ],
  templateUrl: './asset-list.html',
  styleUrl: './asset-list.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssetList {
  private readonly assets = inject(AssetService);
  protected readonly auth = inject(AuthService);
  // The dashboard deep-links here with ?status=in_repair or ?warranty=expiring.
  private readonly params = inject(ActivatedRoute).snapshot.queryParamMap;

  protected readonly statuses = ASSET_STATUSES;
  protected readonly types = ASSET_TYPES;
  protected readonly statusLabels = ASSET_STATUS_LABELS;
  protected readonly typeLabels = ASSET_TYPE_LABELS;
  protected readonly typeLabel = (type: AssetType) => ASSET_TYPE_LABELS[type];

  // Requesters only ever see equipment assigned to them, so status and assignee are noise for them.
  protected readonly columns = computed(() =>
    this.auth.isStaff()
      ? ['tag', 'type', 'device', 'serial', 'status', 'assignee', 'location', 'warranty']
      : ['tag', 'type', 'device', 'serial', 'warranty'],
  );

  protected readonly rows = signal<Asset[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly pageSize = signal(25);
  protected readonly pageIndex = signal(0);

  protected readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true }),
    status: new FormControl<AssetStatus | null>(
      this.fromParam<AssetStatus>(ASSET_STATUSES, 'status'),
    ),
    type: new FormControl<AssetType | null>(null),
    warranty: new FormControl<WarrantyFilter | null>(
      this.fromParam<WarrantyFilter>(['expiring', 'expired'], 'warranty'),
    ),
  });

  constructor() {
    this.filters.valueChanges
      .pipe(debounceTime(250), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        this.pageIndex.set(0);
        void this.reload();
      });
    void this.reload();
  }

  protected get hasFilters(): boolean {
    return Object.values(this.filters.getRawValue()).some(Boolean);
  }

  protected clearFilters(): void {
    this.filters.reset({ q: '', status: null, type: null, warranty: null });
  }

  protected onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    void this.reload();
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    const { q, status, type, warranty } = this.filters.getRawValue();
    try {
      const page = await firstValueFrom(
        this.assets.list({
          q: q.trim() || undefined,
          status: status ?? undefined,
          type: type ?? undefined,
          warranty: warranty ?? undefined,
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

  /** Only accept a query-param value that is a real option, so a hand-edited URL can't inject junk. */
  private fromParam<T extends string>(allowed: readonly T[], name: string): T | null {
    const value = this.params.get(name);
    return allowed.find((a) => a === value) ?? null;
  }
}
