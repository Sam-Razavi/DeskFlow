import { assetTransitionLabel, nextAssetStatuses } from './asset.models';

describe('asset workflow helpers', () => {
  it('never offers "assigned" as a status change', () => {
    for (const status of ['in_stock', 'assigned', 'in_repair', 'retired'] as const) {
      expect(nextAssetStatuses(status)).not.toContain('assigned');
    }
  });

  it('offers repair and retirement from stock or assignment', () => {
    expect(nextAssetStatuses('in_stock')).toEqual(['in_repair', 'retired']);
    expect(nextAssetStatuses('assigned')).toEqual(['in_repair', 'retired']);
  });

  it('lets repaired equipment return to stock and retired equipment go nowhere', () => {
    expect(nextAssetStatuses('in_repair')).toEqual(['in_stock', 'retired']);
    expect(nextAssetStatuses('retired')).toEqual([]);
  });

  it('words buttons by context', () => {
    expect(assetTransitionLabel('in_stock', 'in_repair')).toBe('Send for repair');
    expect(assetTransitionLabel('in_repair', 'in_stock')).toBe('Repaired, return to stock');
    expect(assetTransitionLabel('assigned', 'retired')).toBe('Retire');
  });
});
