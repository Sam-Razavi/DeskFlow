import { Pipe, PipeTransform } from '@angular/core';
import { marked } from 'marked';

/**
 * Turns Markdown into HTML. The result is meant for `[innerHTML]`, where Angular's sanitiser strips
 * scripts, event-handler attributes and `javascript:` URLs, so hostile article text cannot run code.
 */
@Pipe({ name: 'markdown' })
export class MarkdownPipe implements PipeTransform {
  transform(source: string | null | undefined): string {
    if (!source) return '';
    return marked.parse(source, { async: false, gfm: true }) as string;
  }
}
