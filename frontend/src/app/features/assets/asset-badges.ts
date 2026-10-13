import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import {
  ASSET_STATUS_LABELS,
  AssetStatus,
  WARRANTY_LABELS,
  WarrantyState,
} from '../../core/assets/asset.models';

const PILL = `
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 10px;
    border-radius: 999px;
    font: var(--mat-sys-label-medium);
    white-space: nowrap;
    background: var(--mat-sys-surface-container-high);
    color: var(--mat-sys-on-surface-variant);
  }
  .pill mat-icon {
    font-size: 16px;
    width: 16px;
    height: 16px;
    margin-left: -4px;
  }
`;

@Component({
  selector: 'app-asset-status',
  template: `<span class="pill" [class]="'pill pill--' + status()">{{ label() }}</span>`,
  styles: `
    ${PILL}
    .pill--assigned {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
    }
    .pill--in_repair {
      background: #ffe0b2;
      color: #5d3a00;
    }
    .pill--retired {
      background: var(--mat-sys-surface-variant);
      color: var(--mat-sys-outline);
      text-decoration: line-through;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssetStatusBadge {
  readonly status = input.required<AssetStatus>();
  protected readonly label = computed(() => ASSET_STATUS_LABELS[this.status()]);
}

/** Shown only when warranty needs attention; a healthy warranty is the unremarkable default. */
@Component({
  selector: 'app-warranty-badge',
  imports: [MatIconModule],
  template: `
    @if (state(); as s) {
      @if (s !== 'active') {
        <span class="pill" [class]="'pill pill--' + s">
          <mat-icon aria-hidden="true">{{ s === 'expired' ? 'error' : 'warning' }}</mat-icon>
          {{ label() }}
        </span>
      }
    }
  `,
  styles: `
    ${PILL}
    .pill--expiring {
      background: #ffe0b2;
      color: #5d3a00;
    }
    .pill--expired {
      background: var(--mat-sys-error-container);
      color: var(--mat-sys-on-error-container);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WarrantyBadge {
  readonly state = input.required<WarrantyState | null>();
  protected readonly label = computed(() => {
    const s = this.state();
    return s ? WARRANTY_LABELS[s] : '';
  });
}
