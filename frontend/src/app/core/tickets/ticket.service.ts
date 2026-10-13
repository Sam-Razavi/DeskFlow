import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import {
  AuditEntry,
  NewTicket,
  Ticket,
  TicketComment,
  TicketFilters,
  TicketPage,
  TicketStatus,
} from './ticket.models';

@Injectable({ providedIn: 'root' })
export class TicketService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/tickets';

  list(filters: TicketFilters) {
    let params = new HttpParams().set('limit', filters.limit).set('offset', filters.offset);
    if (filters.status) params = params.set('status', filters.status);
    if (filters.priority) params = params.set('priority', filters.priority);
    if (filters.category) params = params.set('category', filters.category);
    if (filters.q) params = params.set('q', filters.q);
    if (filters.unassigned) params = params.set('unassigned', true);
    if (filters.assigneeId !== undefined) params = params.set('assignee_id', filters.assigneeId);
    if (filters.sla) params = params.set('sla', filters.sla);
    return this.http.get<TicketPage>(this.base, { params });
  }

  get(id: number) {
    return this.http.get<Ticket>(`${this.base}/${id}`);
  }

  create(ticket: NewTicket) {
    return this.http.post<Ticket>(this.base, ticket);
  }

  changeStatus(id: number, status: TicketStatus) {
    return this.http.post<Ticket>(`${this.base}/${id}/status`, { status });
  }

  assign(id: number, assigneeId: number | null) {
    return this.http.put<Ticket>(`${this.base}/${id}/assignee`, { assignee_id: assigneeId });
  }

  comments(id: number) {
    return this.http.get<TicketComment[]>(`${this.base}/${id}/comments`);
  }

  addComment(id: number, body: string, isInternal: boolean) {
    return this.http.post<TicketComment>(`${this.base}/${id}/comments`, {
      body,
      is_internal: isInternal,
    });
  }

  history(id: number) {
    return this.http.get<AuditEntry[]>(`${this.base}/${id}/history`);
  }
}
