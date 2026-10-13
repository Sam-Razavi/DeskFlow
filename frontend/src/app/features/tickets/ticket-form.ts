import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import {
  CATEGORIES,
  CATEGORY_LABELS,
  PRIORITIES,
  PRIORITY_LABELS,
} from '../../core/tickets/ticket.models';
import { TicketService } from '../../core/tickets/ticket.service';
import { ArticleSuggestions } from '../kb/article-suggestions';

@Component({
  selector: 'app-ticket-form',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ArticleSuggestions,
  ],
  templateUrl: './ticket-form.html',
  styleUrl: './ticket-form.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketForm {
  private readonly tickets = inject(TicketService);
  private readonly router = inject(Router);
  protected readonly auth = inject(AuthService);

  protected readonly priorities = PRIORITIES;
  protected readonly categories = CATEGORIES;
  protected readonly priorityLabels = PRIORITY_LABELS;
  protected readonly categoryLabels = CATEGORY_LABELS;

  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    title: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(200)]],
    description: ['', [Validators.required, Validators.maxLength(10_000)]],
    category: ['other' as (typeof CATEGORIES)[number], Validators.required],
    priority: ['p3' as (typeof PRIORITIES)[number], Validators.required],
  });

  /** The title as it is typed, used to suggest articles that might make the ticket unnecessary. */
  protected readonly title = toSignal(this.form.controls.title.valueChanges, { initialValue: '' });

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.saving()) return;
    this.saving.set(true);
    this.error.set(null);
    try {
      const ticket = await firstValueFrom(this.tickets.create(this.form.getRawValue()));
      await this.router.navigate(['/tickets', ticket.id]);
    } catch {
      this.error.set('Could not create the ticket. Please try again.');
      this.saving.set(false);
    }
  }
}
