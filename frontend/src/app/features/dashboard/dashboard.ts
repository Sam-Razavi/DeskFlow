import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-dashboard',
  imports: [MatCardModule],
  template: `
    <h1>Welcome back, {{ auth.user()?.full_name }}</h1>
    <mat-card appearance="outlined">
      <mat-card-content>
        Ticket, SLA and asset widgets will appear here as those modules are built.
      </mat-card-content>
    </mat-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dashboard {
  protected readonly auth = inject(AuthService);
}
