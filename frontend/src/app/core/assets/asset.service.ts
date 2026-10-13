import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { AuditEntry, Ticket } from '../tickets/ticket.models';
import { Asset, AssetFilters, AssetInput, AssetPage, AssetStatus, NewAsset } from './asset.models';

@Injectable({ providedIn: 'root' })
export class AssetService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/assets';

  list(filters: AssetFilters) {
    let params = new HttpParams().set('limit', filters.limit).set('offset', filters.offset);
    if (filters.q) params = params.set('q', filters.q);
    if (filters.status) params = params.set('status', filters.status);
    if (filters.type) params = params.set('type', filters.type);
    if (filters.warranty) params = params.set('warranty', filters.warranty);
    if (filters.assignedToId !== undefined)
      params = params.set('assigned_to_id', filters.assignedToId);
    return this.http.get<AssetPage>(this.base, { params });
  }

  get(id: number) {
    return this.http.get<Asset>(`${this.base}/${id}`);
  }

  create(asset: NewAsset) {
    return this.http.post<Asset>(this.base, asset);
  }

  update(id: number, asset: Partial<AssetInput>) {
    return this.http.patch<Asset>(`${this.base}/${id}`, asset);
  }

  changeStatus(id: number, status: AssetStatus) {
    return this.http.post<Asset>(`${this.base}/${id}/status`, { status });
  }

  assign(id: number, assignedToId: number | null) {
    return this.http.put<Asset>(`${this.base}/${id}/assignment`, { assigned_to_id: assignedToId });
  }

  history(id: number) {
    return this.http.get<AuditEntry[]>(`${this.base}/${id}/history`);
  }

  tickets(id: number) {
    return this.http.get<Ticket[]>(`${this.base}/${id}/tickets`);
  }

  // Equipment a ticket is about.
  linked(ticketId: number) {
    return this.http.get<Asset[]>(`/api/tickets/${ticketId}/assets`);
  }

  link(ticketId: number, assetId: number) {
    return this.http.put<Asset>(`/api/tickets/${ticketId}/assets/${assetId}`, null);
  }

  unlink(ticketId: number, assetId: number) {
    return this.http.delete<void>(`/api/tickets/${ticketId}/assets/${assetId}`);
  }
}
