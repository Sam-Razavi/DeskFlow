import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { DashboardService, DashboardSummary } from '../../core/dashboard/dashboard.service';
import { PRIORITIES, PRIORITY_LABELS } from '../../core/tickets/ticket.models';

interface Tile {
  label: string;
  value: number;
  link: string;
  queryParams: Record<string, string>;
  /** Status colour is only applied when there is something to act on (value > 0). */
  tone?: 'critical' | 'warning';
  icon?: string;
}

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, MatButtonModule, MatIconModule, MatTooltipModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dashboard {
  private readonly dashboard = inject(DashboardService);
  protected readonly auth = inject(AuthService);

  protected readonly summary = signal<DashboardSummary | null>(null);
  protected readonly loading = signal(true);
  protected readonly failed = signal(false);
  protected readonly showTable = signal(false);

  protected readonly tiles = computed<Tile[]>(() => {
    const s = this.summary();
    if (!s) return [];
    const awaiting: Tile = {
      label: 'Awaiting confirmation',
      value: s.awaiting_confirmation,
      link: '/tickets',
      queryParams: { status: 'resolved' },
    };
    if (!this.auth.isStaff()) return [awaiting];
    return [
      {
        label: 'SLA breached',
        value: s.sla_breached,
        link: '/tickets',
        queryParams: { sla: 'breached' },
        tone: 'critical',
        icon: 'error',
      },
      {
        label: 'SLA at risk',
        value: s.sla_at_risk,
        link: '/tickets',
        queryParams: { sla: 'at_risk' },
        tone: 'warning',
        icon: 'warning',
      },
      {
        label: 'Unassigned',
        value: s.unassigned,
        link: '/tickets',
        queryParams: { assignment: 'unassigned' },
      },
      {
        label: 'Assigned to me',
        value: s.assigned_to_me,
        link: '/tickets',
        queryParams: { assignment: 'mine' },
      },
      awaiting,
      {
        label: 'Assets in repair',
        value: s.assets_in_repair,
        link: '/assets',
        queryParams: { status: 'in_repair' },
      },
      {
        label: 'Warranty expiring',
        value: s.warranty_expiring,
        link: '/assets',
        queryParams: { warranty: 'expiring' },
        tone: 'warning',
        icon: 'warning',
      },
    ];
  });

  // Bars are scaled to the largest value but capped below 100% so the value label fits at the tip.
  protected readonly bars = computed(() => {
    const s = this.summary();
    if (!s) return [];
    const max = Math.max(1, ...PRIORITIES.map((p) => s.open_by_priority[p]));
    return PRIORITIES.map((p) => {
      const value = s.open_by_priority[p];
      return {
        label: PRIORITY_LABELS[p],
        value,
        width: (value / max) * 85,
        tooltip: `${PRIORITY_LABELS[p]}: ${value} open ${value === 1 ? 'ticket' : 'tickets'}`,
      };
    });
  });

  constructor() {
    void this.load();
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    try {
      this.summary.set(await firstValueFrom(this.dashboard.summary()));
    } catch {
      this.failed.set(true);
    } finally {
      this.loading.set(false);
    }
  }
}
