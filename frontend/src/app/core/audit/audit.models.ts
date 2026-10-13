import { AuditEntry } from '../tickets/ticket.models';

export interface AuditPage {
  items: AuditEntry[];
  total: number;
}

export interface AuditFacets {
  entity_types: string[];
  actions: string[];
}

export interface AuditFilters {
  entityType?: string;
  entityId?: number;
  actorId?: number;
  action?: string;
  from?: string;
  to?: string;
}

export interface AuditQuery extends AuditFilters {
  limit: number;
  offset: number;
}
