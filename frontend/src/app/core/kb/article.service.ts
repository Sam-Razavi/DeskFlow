import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { AuditEntry } from '../tickets/ticket.models';
import {
  Article,
  ArticleFilters,
  ArticleInput,
  ArticlePage,
  ArticleSummary,
} from './article.models';

@Injectable({ providedIn: 'root' })
export class ArticleService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/articles';

  list(filters: ArticleFilters) {
    let params = new HttpParams().set('limit', filters.limit).set('offset', filters.offset);
    if (filters.q) params = params.set('q', filters.q);
    if (filters.category) params = params.set('category', filters.category);
    if (filters.status) params = params.set('status', filters.status);
    return this.http.get<ArticlePage>(this.base, { params });
  }

  /** Published articles that might answer a problem described in free text. */
  suggest(q: string, limit = 4) {
    const params = new HttpParams().set('q', q).set('limit', limit);
    return this.http.get<ArticleSummary[]>(`${this.base}/suggest`, { params });
  }

  get(id: number) {
    return this.http.get<Article>(`${this.base}/${id}`);
  }

  create(article: ArticleInput) {
    return this.http.post<Article>(this.base, article);
  }

  update(id: number, article: Partial<ArticleInput>) {
    return this.http.patch<Article>(`${this.base}/${id}`, article);
  }

  publish(id: number) {
    return this.http.post<Article>(`${this.base}/${id}/publish`, null);
  }

  unpublish(id: number) {
    return this.http.post<Article>(`${this.base}/${id}/unpublish`, null);
  }

  remove(id: number) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  history(id: number) {
    return this.http.get<AuditEntry[]>(`${this.base}/${id}/history`);
  }
}
