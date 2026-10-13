import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { AuditFacets, AuditFilters, AuditPage, AuditQuery } from './audit.models';

function toParams(filters: AuditFilters): HttpParams {
  let params = new HttpParams();
  if (filters.entityType) params = params.set('entity_type', filters.entityType);
  if (filters.entityId !== undefined) params = params.set('entity_id', filters.entityId);
  if (filters.actorId !== undefined) params = params.set('actor_id', filters.actorId);
  if (filters.action) params = params.set('action', filters.action);
  if (filters.from) params = params.set('from', filters.from);
  if (filters.to) params = params.set('to', filters.to);
  return params;
}

@Injectable({ providedIn: 'root' })
export class AuditService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/audit-logs';

  list(query: AuditQuery) {
    const params = toParams(query).set('limit', query.limit).set('offset', query.offset);
    return this.http.get<AuditPage>(this.base, { params });
  }

  facets() {
    return this.http.get<AuditFacets>(`${this.base}/facets`);
  }

  /** The same filters as the list, without paging. The server caps the size of an export. */
  exportCsv(filters: AuditFilters) {
    return this.http.get(`${this.base}/export.csv`, {
      params: toParams(filters),
      responseType: 'blob',
    });
  }
}
