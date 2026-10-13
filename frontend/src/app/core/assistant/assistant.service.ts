import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export interface AssistantReply {
  answer: string | null;
  sources: { id: number; title: string }[];
  /** Why there is no answer: no article matched, or the matches did not cover the problem. */
  reason: 'no_articles' | 'not_covered' | null;
}

@Injectable({ providedIn: 'root' })
export class AssistantService {
  private readonly http = inject(HttpClient);

  suggest(ticketId: number) {
    return this.http.post<AssistantReply>(`/api/tickets/${ticketId}/assistant`, {});
  }
}
