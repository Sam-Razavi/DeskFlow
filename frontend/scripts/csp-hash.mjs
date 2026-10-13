// Prints the Content-Security-Policy hashes for the inline <script> blocks in the built index.html,
// as a shell export for the nginx image to source. Hashing them lets the policy forbid every other
// inline script without using 'unsafe-inline'. Run during the image build, after `ng build`.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const file = process.argv[2];
if (!file) {
  console.error('usage: node csp-hash.mjs <index.html>');
  process.exit(1);
}

const html = readFileSync(file, 'utf8');
// Inline scripts only: those without a src attribute.
const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)];
const hashes = scripts.map(
  ([, body]) => `'sha256-${createHash('sha256').update(body).digest('base64')}'`,
);

console.log(`export CSP_SCRIPT_HASHES="${hashes.join(' ')}"`);
