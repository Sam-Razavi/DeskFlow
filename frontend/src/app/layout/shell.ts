import { BreakpointObserver, Breakpoints } from '@angular/cdk/layout';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { map } from 'rxjs';
import { Role } from '../core/auth/auth.models';
import { AuthService } from '../core/auth/auth.service';

interface NavItem {
  label: string;
  icon: string;
  path: string;
  roles?: Role[];
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', icon: 'dashboard', path: '/' },
  { label: 'Tickets', icon: 'confirmation_number', path: '/tickets' },
  { label: 'Assets', icon: 'devices', path: '/assets', roles: ['agent', 'admin'] },
  { label: 'My equipment', icon: 'laptop_mac', path: '/assets', roles: ['requester'] },
  // Knowledge Base and Audit Log are added as each module lands.
];

@Component({
  selector: 'app-shell',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
  ],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell {
  protected readonly auth = inject(AuthService);

  protected readonly isHandset = toSignal(
    inject(BreakpointObserver)
      .observe(Breakpoints.Handset)
      .pipe(map((result) => result.matches)),
    { initialValue: false },
  );

  protected readonly navItems = computed(() =>
    NAV_ITEMS.filter((item) => !item.roles || this.auth.hasRole(...item.roles)),
  );
}
