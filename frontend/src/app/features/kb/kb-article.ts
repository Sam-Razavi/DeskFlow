import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { Article } from '../../core/kb/article.models';
import { ArticleService } from '../../core/kb/article.service';
import { MarkdownPipe } from '../../core/kb/markdown.pipe';
import { AuditEntry, CATEGORY_LABELS } from '../../core/tickets/ticket.models';

@Component({
  selector: 'app-kb-article',
  imports: [RouterLink, DatePipe, MatButtonModule, MatIconModule, MarkdownPipe],
  templateUrl: './kb-article.html',
  styleUrl: './kb-article.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KbArticle {
  /** Bound from the `:id` route param. */
  readonly id = input.required<string>();

  private readonly articles = inject(ArticleService);
  private readonly router = inject(Router);
  protected readonly auth = inject(AuthService);

  protected readonly article = signal<Article | null>(null);
  protected readonly history = signal<AuditEntry[]>([]);
  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Deleting is permanent, so it takes a second click. */
  protected readonly confirmingDelete = signal(false);

  protected readonly categoryLabels = CATEGORY_LABELS;

  constructor() {
    effect(() => {
      const id = Number(this.id());
      untracked(() => void this.load(id));
    });
  }

  /** Staff can discard drafts; taking a published article down for good is an admin decision. */
  protected canDelete(article: Article): boolean {
    return article.status === 'draft' ? this.auth.isStaff() : this.auth.hasRole('admin');
  }

  protected async publish(): Promise<void> {
    await this.change(() => this.articles.publish(this.requireId()));
  }

  protected async unpublish(): Promise<void> {
    await this.change(() => this.articles.unpublish(this.requireId()));
  }

  protected async remove(): Promise<void> {
    if (!this.confirmingDelete()) {
      this.confirmingDelete.set(true);
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      await firstValueFrom(this.articles.remove(this.requireId()));
      await this.router.navigate(['/kb']);
    } catch (err) {
      this.error.set(this.messageFrom(err, 'The article could not be deleted.'));
      this.confirmingDelete.set(false);
      this.busy.set(false);
    }
  }

  protected describe(entry: AuditEntry): string {
    switch (entry.action) {
      case 'created':
        return 'created the draft';
      case 'published':
        return 'published the article';
      case 'unpublished':
        return 'moved it back to draft';
      default:
        return Object.keys(entry.changes)
          .map((field) => (field === 'body_changed' ? 'edited the text' : `changed the ${field}`))
          .join(', ');
    }
  }

  private requireId(): number {
    return Number(this.id());
  }

  private messageFrom(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } }).error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }

  private async change(call: () => ReturnType<ArticleService['get']>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.article.set(await firstValueFrom(call()));
      this.history.set(await this.fetchHistory(this.requireId()));
    } catch (err) {
      this.error.set(this.messageFrom(err, 'That change could not be saved.'));
    } finally {
      this.busy.set(false);
    }
  }

  private fetchHistory(id: number): Promise<AuditEntry[]> {
    if (!this.auth.isStaff()) return Promise.resolve([]);
    return firstValueFrom(this.articles.history(id)).catch(() => []);
  }

  private async load(id: number): Promise<void> {
    this.loading.set(true);
    this.notFound.set(false);
    this.confirmingDelete.set(false);

    const article = firstValueFrom(this.articles.get(id));
    const history = this.fetchHistory(id);
    try {
      this.article.set(await article);
    } catch {
      this.article.set(null);
      this.notFound.set(true);
      this.loading.set(false);
      return;
    }
    this.history.set(await history);
    this.loading.set(false);
  }
}
