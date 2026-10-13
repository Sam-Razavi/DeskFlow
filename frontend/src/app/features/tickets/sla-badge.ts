import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { SLA_LABELS, SlaState } from '../../core/tickets/ticket.models';

const ICONS: Record<SlaState, string> = {
  ok: 'schedule',
  at_risk: 'warning',
  breached: 'error',
  met: 'check_circle',
  paused: 'pause_circle',
  'n/a': '',
};

/** Colour never carries the meaning alone: every state has its own icon and a text label. */
@Component({
  selector: 'app-sla-badge',
  imports: [MatIconModule],
  template: `
    @if (state() !== 'n/a') {
      <span class="sla" [class]="'sla sla--' + state()">
        <mat-icon aria-hidden="true">{{ icon() }}</mat-icon
        >{{ label() }}
      </span>
    }
  `,
  styles: `
    .sla {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 10px 2px 6px;
      border-radius: 999px;
      font: var(--mat-sys-label-medium);
      white-space: nowrap;
      background: var(--mat-sys-surface-container-high);
      color: var(--mat-sys-on-surface-variant);
    }
    mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .sla--breached {
      background: var(--mat-sys-error-container);
      color: var(--mat-sys-on-error-container);
    }
    .sla--at_risk {
      background: #ffe0b2;
      color: #5d3a00;
    }
    .sla--met {
      background: #c8e6c9;
      color: #1b5e20;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SlaBadge {
  readonly state = input.required<SlaState>();

  protected readonly label = computed(() => SLA_LABELS[this.state()]);
  protected readonly icon = computed(() => ICONS[this.state()]);
}
