import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { startWith } from 'rxjs';
import { firstValueFrom } from 'rxjs';
import { ArticleService } from '../../core/kb/article.service';
import { MarkdownPipe } from '../../core/kb/markdown.pipe';
import { CATEGORIES, Category, CATEGORY_LABELS } from '../../core/tickets/ticket.models';

@Component({
  selector: 'app-kb-form',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MarkdownPipe,
  ],
  templateUrl: './kb-form.html',
  styleUrl: './kb-form.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KbForm {
  /** Bound from the `:id` route param; absent when writing a new article. */
  readonly id = input<string>();

  private readonly articles = inject(ArticleService);
  private readonly router = inject(Router);

  protected readonly categories = CATEGORIES;
  protected readonly categoryLabels = CATEGORY_LABELS;
  protected readonly saving = signal(false);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    title: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(200)]],
    category: ['other' as Category, Validators.required],
    body: ['', [Validators.required, Validators.maxLength(50_000)]],
  });

  /** What the preview shows: the article text as the reader will see it. */
  protected readonly preview = toSignal(
    this.form.controls.body.valueChanges.pipe(startWith(this.form.controls.body.value)),
    { initialValue: '' },
  );

  protected get editing(): boolean {
    return this.id() !== undefined;
  }

  constructor() {
    effect(() => {
      const id = this.id();
      if (id !== undefined) void this.load(Number(id));
    });
  }

  private async load(id: number): Promise<void> {
    this.loading.set(true);
    try {
      const a = await firstValueFrom(this.articles.get(id));
      this.form.setValue({ title: a.title, category: a.category, body: a.body });
    } catch {
      this.error.set('Could not load this article.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.saving()) return;
    this.saving.set(true);
    this.error.set(null);
    const value = this.form.getRawValue();
    try {
      const saved = this.editing
        ? await firstValueFrom(this.articles.update(Number(this.id()), value))
        : await firstValueFrom(this.articles.create(value));
      await this.router.navigate(['/kb', saved.id]);
    } catch (err) {
      this.error.set(
        err instanceof HttpErrorResponse && err.status === 403
          ? 'You do not have permission to edit articles.'
          : 'Could not save the article. Please check it and try again.',
      );
      this.saving.set(false);
    }
  }
}
