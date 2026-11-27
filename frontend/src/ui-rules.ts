/**
 * Main-view display rules, shared by unit tests (jsdom) and the live-page check
 * (scripts/verify_ui_rules.cjs). Text inside [data-ui-guard-skip] (Audit details, the global
 * footer, the header "Synthetic data" badge) is exempt.
 */
import { MODEL_FEATURES } from './terminology';

export type Violation = { rule: string; match: string };

export const RULES: readonly { rule: string; pattern: RegExp }[] = [
  // Money or measures with more than 2 decimals ("USD 72,000.00000000", "0.0089").
  // Regulation section numbers such as "§ 1020.320" are identifiers, not decimals.
  { rule: 'more_than_2_decimals', pattern: /(?<!§\s*\d*)\d\.\d{3,}\b/g },
  { rule: 'midnight_time', pattern: /\b00:00:00\b/g },
  { rule: 'sha256', pattern: /\b[0-9a-f]{64}\b/gi },
  {
    rule: 'uuid',
    pattern:
      /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
  },
  {
    rule: 'model_field_name',
    // camelCase field names only; "income", "state" and "PEP" are ordinary words.
    pattern: new RegExp(
      `\\b(?:${MODEL_FEATURES.filter((n) => /[a-z][A-Z0-9]/.test(n)).join('|')})\\b`,
      'g',
    ),
  },
  {
    rule: 'disclaimer_outside_footer',
    pattern:
      /Human review required|No automatic case actions|Synthetic data|Not regulatory guidance|Academic demo/gi,
  },
];

export function findViolations(text: string): Violation[] {
  const found: Violation[] = [];
  for (const { rule, pattern } of RULES) {
    for (const match of text.matchAll(pattern))
      found.push({ rule, match: match[0] });
  }
  return found;
}

/** Visible main-view text of a rendered tree, excluding exempt regions. */
export function mainViewText(root: Element): string {
  const clone = root.cloneNode(true) as Element;
  clone
    .querySelectorAll('[data-ui-guard-skip], script, style')
    .forEach((n) => n.remove());
  // Join text nodes with spaces so adjacent cells never merge into one token.
  const walker = root.ownerDocument.createTreeWalker(
    clone,
    NodeFilter.SHOW_TEXT,
  );
  const parts: string[] = [];
  while (walker.nextNode()) parts.push(walker.currentNode.nodeValue ?? '');
  return parts.join(' ');
}
