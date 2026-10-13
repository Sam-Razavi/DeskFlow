import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import {
  Priority,
  PRIORITY_LABELS,
  STATUS_LABELS,
  TicketStatus,
} from '../../core/tickets/ticket.models';

/** Small coloured pill used for both statuses and priorities. */
@Component({
  selector: 'app-badge',
  template: `<span class="badge" [class]="'badge badge--' + kind()">{{ label() }}</span>`,
  styles: `
    .badge {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 999px;
      font: var(--mat-sys-label-medium);
      white-space: nowrap;
      background: var(--mat-sys-surface-container-high);
      color: var(--mat-sys-on-surface-variant);
    }
    .badge--p1 {
      background: var(--mat-sys-error-container);
      color: var(--mat-sys-on-error-container);
    }
    .badge--p2,
    .badge--pending {
      background: #ffe0b2;
      color: #5d3a00;
    }
    .badge--in_progress,
    .badge--new {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
    }
    .badge--resolved {
      background: #c8e6c9;
      color: #1b5e20;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Badge {
  readonly value = input.required<TicketStatus | Priority>();

  protected readonly kind = computed(() => this.value());
  protected readonly label = computed(() => {
    const v = this.value();
    return v in STATUS_LABELS ? STATUS_LABELS[v as TicketStatus] : PRIORITY_LABELS[v as Priority];
  });
}
