import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { catchError, debounceTime, distinctUntilChanged, map, of, switchMap } from 'rxjs';
import { ArticleSummary } from '../../core/kb/article.models';
import { ArticleService } from '../../core/kb/article.service';

const MIN_LENGTH = 4;

/**
 * "These articles might help": published knowledge base articles matching some free text, such as
 * the title of a ticket being written. Shows nothing until there is something worth showing.
 */
@Component({
  selector: 'app-article-suggestions',
  imports: [RouterLink, MatCardModule, MatIconModule],
  template: `
    @if (suggestions().length) {
      <mat-card appearance="outlined" class="suggestions">
        <mat-card-content>
          <h2 class="suggestions__title">
            <mat-icon aria-hidden="true">lightbulb</mat-icon>{{ heading() }}
          </h2>
          <ul class="suggestions__list">
            @for (a of suggestions(); track a.id) {
              <li>
                <!-- A new tab, so following a suggestion never loses a half-written ticket. -->
                <a [routerLink]="['/kb', a.id]" target="_blank" rel="noopener">{{ a.title }}</a>
              </li>
            }
          </ul>
        </mat-card-content>
      </mat-card>
    }
  `,
  styles: `
    .suggestions {
      margin: 8px 0 16px;
      background: var(--mat-sys-surface-container-lowest);
    }
    .suggestions__title {
      display: flex;
      align-items: center;
      gap: 6px;
      font: var(--mat-sys-title-small);
      margin: 0 0 8px;
    }
    .suggestions__list {
      margin: 0;
      padding-left: 20px;
    }
    .suggestions__list li {
      padding: 2px 0;
    }
    .suggestions__list a {
      color: var(--mat-sys-primary);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ArticleSuggestions {
  readonly query = input<string | null | undefined>('');
  readonly heading = input('These articles might help');
  readonly limit = input(4);

  private readonly articles = inject(ArticleService);

  protected readonly suggestions = toSignal(
    toObservable(this.query).pipe(
      map((q) => (q ?? '').trim()),
      debounceTime(400), // wait for a pause in typing before asking
      distinctUntilChanged(),
      // switchMap drops the answer to a stale query if a newer one is already on its way.
      switchMap((q) =>
        q.length < MIN_LENGTH
          ? of([] as ArticleSummary[])
          : this.articles
              .suggest(q, this.limit())
              .pipe(catchError(() => of([] as ArticleSummary[]))),
      ),
    ),
    { initialValue: [] as ArticleSummary[] },
  );
}
