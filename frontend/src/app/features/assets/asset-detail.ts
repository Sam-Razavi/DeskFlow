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
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import {
  Asset,
  ASSET_TYPE_LABELS,
  AssetStatus,
  assetTransitionLabel,
  nextAssetStatuses,
} from '../../core/assets/asset.models';
import { AssetService } from '../../core/assets/asset.service';
import { User } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import {
  AuditEntry,
  PRIORITY_LABELS,
  STATUS_LABELS,
  Ticket,
} from '../../core/tickets/ticket.models';
import { UserService } from '../../core/users/user.service';
import { Badge } from '../tickets/status-badge';
import { AssetStatusBadge, WarrantyBadge } from './asset-badges';

const IN_STOCK_OPTION = 0;

@Component({
  selector: 'app-asset-detail',
  imports: [
    RouterLink,
    DatePipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatSelectModule,
    AssetStatusBadge,
    WarrantyBadge,
    Badge,
  ],
  templateUrl: './asset-detail.html',
  styleUrl: './asset-detail.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssetDetail {
  /** Bound from the `:id` route param. */
  readonly id = input.required<string>();

  private readonly assets = inject(AssetService);
  private readonly users = inject(UserService);
  protected readonly auth = inject(AuthService);

  protected readonly asset = signal<Asset | null>(null);
  protected readonly history = signal<AuditEntry[]>([]);
  protected readonly tickets = signal<Ticket[]>([]);
  protected readonly people = signal<User[]>([]);
  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Retiring is permanent, so it takes a second click. */
  protected readonly confirmingRetire = signal(false);

  protected readonly typeLabels = ASSET_TYPE_LABELS;
  protected readonly inStock = IN_STOCK_OPTION;
  protected readonly transitionLabel = assetTransitionLabel;
  protected readonly statusLabels = STATUS_LABELS;
  protected readonly priorityLabels = PRIORITY_LABELS;

  protected readonly actions = computed(() => {
    const a = this.asset();
    return a && this.auth.isStaff() ? nextAssetStatuses(a.status) : [];
  });
  protected readonly canAssign = computed(() => {
    const status = this.asset()?.status;
    return this.auth.isStaff() && (status === 'in_stock' || status === 'assigned');
  });

  constructor() {
    effect(() => {
      const id = Number(this.id());
      untracked(() => void this.load(id));
    });
  }

  protected async changeStatus(status: AssetStatus): Promise<void> {
    if (status === 'retired' && !this.confirmingRetire()) {
      this.confirmingRetire.set(true);
      return;
    }
    this.confirmingRetire.set(false);
    await this.mutate(() => this.assets.changeStatus(this.requireId(), status));
  }

  protected async assign(userId: number): Promise<void> {
    await this.mutate(() =>
      this.assets.assign(this.requireId(), userId === IN_STOCK_OPTION ? null : userId),
    );
  }

  protected describe(entry: AuditEntry): string {
    switch (entry.action) {
      case 'created':
        return 'added the asset';
      case 'ticket_linked':
        return `linked ticket #${String(entry.changes['ticket_id'])}`;
      case 'ticket_unlinked':
        return `unlinked ticket #${String(entry.changes['ticket_id'])}`;
      default:
        return Object.entries(entry.changes)
          .map(([field, value]) => this.formatChange(field, value))
          .join('; ');
    }
  }

  private formatChange(field: string, value: unknown): string {
    const [from, to] = Array.isArray(value) ? value : [null, value];
    const label = field === 'assigned_to_id' ? 'assigned to' : field.replace(/_/g, ' ');
    return `${label}: ${this.formatValue(field, from)} → ${this.formatValue(field, to)}`;
  }

  private formatValue(field: string, value: unknown): string {
    if (value === null || value === undefined || value === '') return '—';
    if (field === 'assigned_to_id') {
      return this.people().find((u) => u.id === value)?.full_name ?? `user #${String(value)}`;
    }
    return String(value).replace(/_/g, ' ');
  }

  private requireId(): number {
    return Number(this.id());
  }

  private fetchExtras(id: number) {
    if (!this.auth.isStaff()) return Promise.resolve(null);
    return Promise.all([
      firstValueFrom(this.assets.history(id)),
      firstValueFrom(this.assets.tickets(id)),
    ]).catch(() => null);
  }

  private async mutate(call: () => ReturnType<AssetService['get']>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.asset.set(await firstValueFrom(call()));
      const extras = await this.fetchExtras(this.requireId());
      if (extras) {
        this.history.set(extras[0]);
        this.tickets.set(extras[1]);
      }
    } catch (err) {
      const detail = (err as { error?: { detail?: unknown } }).error?.detail;
      this.error.set(typeof detail === 'string' ? detail : 'That change could not be saved.');
    } finally {
      this.busy.set(false);
    }
  }

  /** Everything is requested at once; only the asset itself decides "not found". */
  private async load(id: number): Promise<void> {
    this.loading.set(true);
    this.notFound.set(false);
    this.confirmingRetire.set(false);

    const asset = firstValueFrom(this.assets.get(id));
    const extras = this.fetchExtras(id);
    const people =
      this.auth.isStaff() && this.people().length === 0
        ? firstValueFrom(this.users.list()).catch(() => null)
        : Promise.resolve(null);

    try {
      this.asset.set(await asset);
    } catch {
      this.asset.set(null);
      this.notFound.set(true);
      this.loading.set(false);
      return;
    }

    const [loaded, users] = await Promise.all([extras, people]);
    if (loaded) {
      this.history.set(loaded[0]);
      this.tickets.set(loaded[1]);
    }
    if (users) this.people.set(users.filter((u) => u.is_active));
    this.loading.set(false);
  }
}
