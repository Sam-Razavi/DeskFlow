import { UserBrief } from '../tickets/ticket.models';

export type AssetType =
  'laptop' | 'desktop' | 'monitor' | 'phone' | 'printer' | 'network' | 'peripheral' | 'other';
export type AssetStatus = 'in_stock' | 'assigned' | 'in_repair' | 'retired';
export type WarrantyState = 'active' | 'expiring' | 'expired';
export type WarrantyFilter = 'expiring' | 'expired';

export interface Asset {
  id: number;
  asset_tag: string;
  type: AssetType;
  manufacturer: string;
  model: string;
  serial_number: string | null;
  status: AssetStatus;
  assigned_to: UserBrief | null;
  location: string | null;
  purchase_date: string | null;
  warranty_expires_on: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  warranty_state: WarrantyState | null;
}

export interface AssetPage {
  items: Asset[];
  total: number;
}

export interface AssetFilters {
  q?: string;
  status?: AssetStatus;
  type?: AssetType;
  warranty?: WarrantyFilter;
  assignedToId?: number;
  limit: number;
  offset: number;
}

/** Fields shared by create and edit. A blank optional field is sent as null so it can be cleared. */
export interface AssetInput {
  type: AssetType;
  manufacturer: string;
  model: string;
  serial_number: string | null;
  location: string | null;
  purchase_date: string | null;
  warranty_expires_on: string | null;
  notes: string | null;
}

export interface NewAsset extends AssetInput {
  asset_tag: string | null;
}

export const ASSET_TYPES: readonly AssetType[] = [
  'laptop',
  'desktop',
  'monitor',
  'phone',
  'printer',
  'network',
  'peripheral',
  'other',
];
export const ASSET_STATUSES: readonly AssetStatus[] = [
  'in_stock',
  'assigned',
  'in_repair',
  'retired',
];

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  laptop: 'Laptop',
  desktop: 'Desktop',
  monitor: 'Monitor',
  phone: 'Phone',
  printer: 'Printer',
  network: 'Network device',
  peripheral: 'Peripheral',
  other: 'Other',
};

export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  in_stock: 'In stock',
  assigned: 'Assigned',
  in_repair: 'In repair',
  retired: 'Retired',
};

export const WARRANTY_LABELS: Record<WarrantyState, string> = {
  active: 'In warranty',
  expiring: 'Expiring soon',
  expired: 'Expired',
};

// Mirrors backend/app/services/asset_workflow.py. Assigned is never offered here: assigning and
// returning to stock go through the assignment control, which is the only way in or out of it.
const TRANSITIONS: Record<AssetStatus, AssetStatus[]> = {
  in_stock: ['in_repair', 'retired'],
  assigned: ['in_repair', 'retired'],
  in_repair: ['in_stock', 'retired'],
  retired: [],
};

export const nextAssetStatuses = (current: AssetStatus): AssetStatus[] => TRANSITIONS[current];

export function assetTransitionLabel(from: AssetStatus, to: AssetStatus): string {
  if (to === 'in_repair') return 'Send for repair';
  if (to === 'retired') return 'Retire';
  return from === 'in_repair' ? 'Repaired, return to stock' : 'Return to stock';
}
