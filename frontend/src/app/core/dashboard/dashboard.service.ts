import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Priority } from '../tickets/ticket.models';

export interface DashboardSummary {
  open_total: number;
  open_by_priority: Record<Priority, number>;
  sla_breached: number;
  sla_at_risk: number;
  unassigned: number;
  assigned_to_me: number;
  awaiting_confirmation: number;
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly http = inject(HttpClient);

  summary() {
    return this.http.get<DashboardSummary>('/api/dashboard');
  }
}
