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
import { Asset, ASSET_TYPE_LABELS } from '../../core/assets/asset.models';
import { AssetService } from '../../core/assets/asset.service';
import { AuthService } from '../../core/auth/auth.service';

/**
 * The equipment a ticket is about. Staff pick from what is assigned to the ticket's requester;
 * requesters pick from their own equipment (the API only ever returns theirs).
 */
@Component({
  selector: 'app-ticket-assets',
  imports: [
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatSelectModule,
  ],
  template: `
    @if (visible()) {
      <mat-card appearance="outlined" class="card">
        <mat-card-content>
          <h2 class="card__title">Related equipment</h2>

          @if (error(); as message) {
            <p class="card__error" role="alert">{{ message }}</p>
          }

          <ul class="list">
            @for (a of linked(); track a.id) {
              <li>
                <a [routerLink]="['/assets', a.id]">{{ a.asset_tag }}</a>
                <span class="list__device"
                  >{{ typeLabels[a.type] }} · {{ a.manufacturer }} {{ a.model }}</span
                >
                @if (!closed()) {
                  <button
                    mat-icon-button
                    type="button"
                    [attr.aria-label]="'Unlink ' + a.asset_tag"
                    [disabled]="busy()"
                    (click)="unlink(a)"
                  >
                    <mat-icon>close</mat-icon>
                  </button>
                }
              </li>
            } @empty {
              <li class="muted">No equipment linked.</li>
            }
          </ul>

          @if (!closed() && available().length) {
            <mat-form-field subscriptSizing="dynamic" class="card__select">
              <mat-label>Link equipment</mat-label>
              <mat-select (selectionChange)="link($event.value)" [disabled]="busy()">
                @for (a of available(); track a.id) {
                  <mat-option [value]="a"
                    >{{ a.asset_tag }} · {{ a.manufacturer }} {{ a.model }}</mat-option
                  >
                }
              </mat-select>
            </mat-form-field>
          }
        </mat-card-content>
      </mat-card>
    }
  `,
  styles: `
    .card {
      margin-top: 16px;
    }
    .card__title {
      font: var(--mat-sys-title-medium);
      margin: 0 0 8px;
    }
    .card__error {
      color: var(--mat-sys-error);
    }
    .card__select {
      width: 100%;
      margin-top: 8px;
    }
    .list {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .list li {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 0;
    }
    .list a {
      color: var(--mat-sys-primary);
      text-decoration: none;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
    }
    .list__device {
      flex: 1;
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-body-small);
    }
    .muted {
      color: var(--mat-sys-on-surface-variant);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketAssets {
  readonly ticketId = input.required<number>();
  readonly requesterId = input.required<number>();
  readonly closed = input(false);

  private readonly assets = inject(AssetService);
  private readonly auth = inject(AuthService);

  protected readonly typeLabels = ASSET_TYPE_LABELS;
  protected readonly linked = signal<Asset[]>([]);
  private readonly candidates = signal<Asset[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly available = computed(() => {
    const taken = new Set(this.linked().map((a) => a.id));
    return this.candidates().filter((a) => !taken.has(a.id));
  });

  // A requester with nothing to link and nothing linked has no use for the panel.
  protected readonly visible = computed(
    () => this.auth.isStaff() || this.linked().length > 0 || this.available().length > 0,
  );

  constructor() {
    effect(() => {
      const id = this.ticketId();
      const requester = this.requesterId();
      untracked(() => void this.load(id, requester));
    });
  }

  protected async link(asset: Asset): Promise<void> {
    await this.change(async () => {
      await firstValueFrom(this.assets.link(this.ticketId(), asset.id));
      this.linked.update((list) =>
        [...list, asset].sort((a, b) => a.asset_tag.localeCompare(b.asset_tag)),
      );
    });
  }

  protected async unlink(asset: Asset): Promise<void> {
    await this.change(async () => {
      await firstValueFrom(this.assets.unlink(this.ticketId(), asset.id));
      this.linked.update((list) => list.filter((a) => a.id !== asset.id));
    });
  }

  private async change(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch {
      this.error.set('That change could not be saved.');
    } finally {
      this.busy.set(false);
    }
  }

  private async load(ticketId: number, requesterId: number): Promise<void> {
    const staff = this.auth.isStaff();
    const [linked, candidates] = await Promise.all([
      firstValueFrom(this.assets.linked(ticketId)).catch(() => null),
      firstValueFrom(
        this.assets.list({ assignedToId: staff ? requesterId : undefined, limit: 100, offset: 0 }),
      ).catch(() => null),
    ]);
    if (linked) this.linked.set(linked);
    if (candidates) this.candidates.set(candidates.items);
  }
}
