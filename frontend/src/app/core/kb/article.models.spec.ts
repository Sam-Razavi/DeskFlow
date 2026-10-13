import { highlightFragments } from './article.models';

describe('highlightFragments', () => {
  it('splits a snippet into plain and highlighted pieces', () => {
    expect(highlightFragments('Restart the ⟦VPN⟧ client, then the ⟦VPN⟧ tunnel.')).toEqual([
      { text: 'Restart the ', match: false },
      { text: 'VPN', match: true },
      { text: ' client, then the ', match: false },
      { text: 'VPN', match: true },
      { text: ' tunnel.', match: false },
    ]);
  });

  it('returns plain text unchanged', () => {
    expect(highlightFragments('Nothing marked here')).toEqual([
      { text: 'Nothing marked here', match: false },
    ]);
  });

  it('handles a match at either end and an empty snippet', () => {
    expect(highlightFragments('⟦Start⟧ and ⟦end⟧')).toEqual([
      { text: 'Start', match: true },
      { text: ' and ', match: false },
      { text: 'end', match: true },
    ]);
    expect(highlightFragments('')).toEqual([]);
  });

  it('never shows a stray marker if one is unbalanced', () => {
    expect(highlightFragments('Broken \u27e6marker never closed')).toEqual([
      { text: 'Broken marker never closed', match: false },
    ]);
    expect(highlightFragments('Closing only⟧ here')).toEqual([
      { text: 'Closing only here', match: false },
    ]);
  });

  it('keeps markup-looking text as plain text for the template to escape', () => {
    expect(highlightFragments('<b>bold</b> ⟦x⟧')[0]).toEqual({
      text: '<b>bold</b> ',
      match: false,
    });
  });
});
