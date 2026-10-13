import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { User } from '../auth/auth.models';

@Injectable({ providedIn: 'root' })
export class UserService {
  private readonly http = inject(HttpClient);

  /** Staff-only endpoint; requesters get a 403. */
  list() {
    return this.http.get<User[]>('/api/users');
  }
}
