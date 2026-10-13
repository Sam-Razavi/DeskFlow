import { MarkdownPipe } from './markdown.pipe';

describe('MarkdownPipe', () => {
  const pipe = new MarkdownPipe();

  it('renders headings, emphasis, lists and code', () => {
    const html = pipe.transform('## Steps\n\n1. Open **Settings**\n2. Run `ipconfig`');
    expect(html).toContain('<h2');
    expect(html).toContain('<strong>Settings</strong>');
    expect(html).toContain('<ol>');
    expect(html).toContain('<code>ipconfig</code>');
  });

  it('renders tables and fenced code blocks', () => {
    const table = pipe.transform('| A | B |\n|---|---|\n| 1 | 2 |');
    expect(table).toContain('<table>');
    expect(table).toContain('<td>1</td>');
    expect(pipe.transform('```\nipconfig /flushdns\n```')).toContain('<pre><code>');
  });

  it('gives nothing for empty input', () => {
    expect(pipe.transform('')).toBe('');
    expect(pipe.transform(null)).toBe('');
    expect(pipe.transform(undefined)).toBe('');
  });
});
