import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AssistantReply, AssistantService } from '../../core/assistant/assistant.service';
import { MarkdownPipe } from '../../core/kb/markdown.pipe';

const NO_ANSWER: Record<string, string> = {
  no_articles:
    'No published knowledge-base article matches this ticket, so there is nothing to suggest.',
  not_covered: 'The matching articles do not cover this problem, so no suggestion was made.',
};

/**
 * Troubleshooting steps for a ticket, written from published knowledge-base articles only. It runs
 * on request (each run costs money) and always lists the articles the steps came from.
 */
@Component({
  selector: 'app-ticket-assistant',
  imports: [
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MarkdownPipe,
  ],
  template: `
    <mat-card appearance="outlined" class="card">
      <mat-card-content>
        <h2 class="card__title"><mat-icon aria-hidden="true">auto_awesome</mat-icon>Assistant</h2>
        <p class="muted">
          Suggests steps using only published knowledge-base articles. It can be wrong, so check the
          sources.
        </p>

        @if (error(); as message) {
          <p class="card__error" role="alert">{{ message }}</p>
        }

        @if (reply(); as r) {
          @if (r.answer) {
            <div class="answer" [innerHTML]="r.answer | markdown"></div>
            <p class="sources">
              Sources:
              @for (s of r.sources; track s.id; let last = $last) {
                <a [routerLink]="['/kb', s.id]" target="_blank" rel="noopener">{{ s.title }}</a
                >{{ last ? '' : ', ' }}
              }
            </p>
          } @else {
            <p class="muted" role="status">{{ noAnswer(r) }}</p>
          }
        }

        <button mat-stroked-button type="button" (click)="ask()" [disabled]="busy()">
          @if (busy()) {
            <mat-spinner diameter="18" />
            Thinking…
          } @else {
            {{ reply() ? 'Ask again' : 'Suggest steps' }}
          }
        </button>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .card {
      margin-top: 16px;
    }
    .card__title {
      display: flex;
      align-items: center;
      gap: 6px;
      font: var(--mat-sys-title-medium);
      margin: 0 0 4px;
    }
    .card__error {
      color: var(--mat-sys-error);
    }
    .muted {
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-body-small);
    }
    .answer {
      margin: 8px 0;
    }
    .sources {
      font: var(--mat-sys-body-small);
      margin: 0 0 12px;
    }
    .sources a {
      color: var(--mat-sys-primary);
    }
    button mat-spinner {
      display: inline-block;
      margin-right: 8px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketAssistant {
  readonly ticketId = input.required<number>();

  private readonly assistant = inject(AssistantService);

  protected readonly reply = signal<AssistantReply | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected noAnswer(r: AssistantReply): string {
    return NO_ANSWER[r.reason ?? ''] ?? 'No suggestion was made.';
  }

  protected async ask(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.reply.set(await firstValueFrom(this.assistant.suggest(this.ticketId())));
    } catch (e) {
      this.reply.set(null);
      this.error.set(this.describe(e));
    } finally {
      this.busy.set(false);
    }
  }

  private describe(e: unknown): string {
    const status = e instanceof HttpErrorResponse ? e.status : 0;
    if (status === 503) return 'The assistant has not been set up on this server.';
    if (status === 429)
      return e instanceof HttpErrorResponse && e.error?.detail
        ? e.error.detail
        : 'You have used the assistant too often. Try again later.';
    return 'The assistant could not answer right now. Try again in a moment.';
  }
}
