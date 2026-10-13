import { Category, UserBrief } from '../tickets/ticket.models';

export type ArticleStatus = 'draft' | 'published';

export interface ArticleSummary {
  id: number;
  title: string;
  category: Category;
  status: ArticleStatus;
  author: UserBrief;
  published_at: string | null;
  updated_at: string;
  /** A search match with the matched words wrapped in the highlight characters, or an excerpt. */
  snippet: string;
}

export interface Article {
  id: number;
  title: string;
  body: string;
  category: Category;
  status: ArticleStatus;
  author: UserBrief;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArticlePage {
  items: ArticleSummary[];
  total: number;
}

export interface ArticleFilters {
  q?: string;
  category?: Category;
  status?: ArticleStatus;
  limit: number;
  offset: number;
}

export interface ArticleInput {
  title: string;
  body: string;
  category: Category;
}

export const ARTICLE_STATUS_LABELS: Record<ArticleStatus, string> = {
  draft: 'Draft',
  published: 'Published',
};

// The API marks search matches with these characters rather than HTML, so the text it returns is
// never markup. They are split out here and rendered as <mark> by the template.
const HIGHLIGHT_START = '⟦';
const HIGHLIGHT_END = '⟧';

export interface Fragment {
  text: string;
  match: boolean;
}

/** Splits a snippet into plain and highlighted pieces. Unbalanced markers degrade to plain text. */
export function highlightFragments(snippet: string): Fragment[] {
  const fragments: Fragment[] = [];
  let rest = snippet;
  while (rest) {
    const start = rest.indexOf(HIGHLIGHT_START);
    const end = start === -1 ? -1 : rest.indexOf(HIGHLIGHT_END, start);
    if (start === -1 || end === -1) {
      fragments.push({ text: stripMarkers(rest), match: false });
      break;
    }
    if (start > 0) fragments.push({ text: stripMarkers(rest.slice(0, start)), match: false });
    fragments.push({ text: stripMarkers(rest.slice(start + 1, end)), match: true });
    rest = rest.slice(end + 1);
  }
  return fragments.filter((f) => f.text);
}

const stripMarkers = (text: string) =>
  text.replaceAll(HIGHLIGHT_START, '').replaceAll(HIGHLIGHT_END, '');
