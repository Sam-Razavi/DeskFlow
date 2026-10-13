import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { debounceTime, firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import {
  ARTICLE_STATUS_LABELS,
  ArticleStatus,
  ArticleSummary,
  highlightFragments,
} from '../../core/kb/article.models';
import { ArticleService } from '../../core/kb/article.service';
import { CATEGORIES, Category, CATEGORY_LABELS } from '../../core/tickets/ticket.models';

@Component({
  selector: 'app-kb-list',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatSelectModule,
  ],
  templateUrl: './kb-list.html',
  styleUrl: './kb-list.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KbList {
  private readonly articles = inject(ArticleService);
  protected readonly auth = inject(AuthService);
  private readonly params = inject(ActivatedRoute).snapshot.queryParamMap;

  protected readonly categories = CATEGORIES;
  protected readonly categoryLabels = CATEGORY_LABELS;
  protected readonly statusLabels = ARTICLE_STATUS_LABELS;
  protected readonly fragments = highlightFragments;

  protected readonly rows = signal<ArticleSummary[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly pageSize = signal(10);
  protected readonly pageIndex = signal(0);
  /** The search the current results answer, which the empty state quotes back. */
  protected readonly searched = signal('');

  protected readonly filters = new FormGroup({
    q: new FormControl((this.params.get('q') ?? '').slice(0, 200), { nonNullable: true }),
    category: new FormControl<Category | null>(this.fromParam<Category>(CATEGORIES, 'category')),
    status: new FormControl<ArticleStatus | null>(
      this.fromParam<ArticleStatus>(['draft', 'published'], 'status'),
    ),
  });

  constructor() {
    this.filters.valueChanges
      .pipe(debounceTime(300), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        this.pageIndex.set(0);
        void this.reload();
      });
    void this.reload();
  }

  protected get hasFilters(): boolean {
    return Object.values(this.filters.getRawValue()).some(Boolean);
  }

  protected clearFilters(): void {
    this.filters.reset({ q: '', category: null, status: null });
  }

  protected onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    void this.reload();
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    const { q, category, status } = this.filters.getRawValue();
    const query = q.trim();
    try {
      const page = await firstValueFrom(
        this.articles.list({
          q: query || undefined,
          category: category ?? undefined,
          // Requesters only ever get published articles, so the filter is for staff.
          status: this.auth.isStaff() ? (status ?? undefined) : undefined,
          limit: this.pageSize(),
          offset: this.pageIndex() * this.pageSize(),
        }),
      );
      this.rows.set(page.items);
      this.total.set(page.total);
      this.searched.set(query);
    } catch {
      this.failed.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  private fromParam<T extends string>(allowed: readonly T[], name: string): T | null {
    const value = this.params.get(name);
    return allowed.find((a) => a === value) ?? null;
  }
}
