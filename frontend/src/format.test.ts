import { describe, expect, it } from 'vitest';
import {
  formatDate,
  formatDateTime,
  inclusiveEnd,
  isDateOnly,
  money,
  percent1,
  periodLabel,
  pp1,
  relativeTime,
  roundDecimal,
  scorePercent,
  shortId,
  subtractDecimal,
  utcText,
} from './format';
import { FEATURE_LABELS, MODEL_FEATURES, featureLabel } from './terminology';
import { findViolations } from './ui-rules';

describe('money', () => {
  it('uses a currency symbol, thousands separators and at most 2 decimals', () => {
    expect(money('72000.00000000', 'USD', { whole: true })).toBe('$72,000');
    expect(money('243.16000000', 'USD')).toBe('$243.16');
    expect(money('1234.565', 'USD')).toBe('$1,234.57');
    expect(money('0.004', 'EUR')).toBe('€0.00');
    expect(money('-163.25000000', 'USD')).toBe('−$163.25');
    expect(money('163.25', 'USD', { signed: true })).toBe('+$163.25');
    expect(money('0', 'USD', { signed: true })).toBe('$0.00');
    expect(money(null, 'USD')).toBe('Not available');
  });

  it('rounds exact decimal strings without floating point error', () => {
    expect(roundDecimal('0.125', 2)).toBe('0.13');
    expect(roundDecimal('999999999999999999.995', 2)).toBe(
      '1000000000000000000.00',
    );
    expect(roundDecimal('-0.004', 2)).toBe('0.00');
    expect(subtractDecimal('243.16000000', '406.41000000')).toBe(
      '-163.25000000',
    );
    expect(subtractDecimal('10', '2.5')).toBe('7.5');
  });

  it('never shows more than 2 decimals for any amount', () => {
    for (const v of ['1.23456789', '0.00000001', '12345678.9999', '5']) {
      expect(money(v, 'USD')).not.toMatch(/\.\d{3,}/);
    }
  });
});

describe('dates', () => {
  it('shows dates without a midnight time and real timestamps with a zone', () => {
    expect(isDateOnly('2025-09-23T00:00:00Z')).toBe(true);
    expect(formatDate('2025-09-23T00:00:00Z')).toBe('Sep 23, 2025');
    expect(formatDateTime('2025-09-23T00:00:00Z')).toBe('Sep 23, 2025');
    const stamp = formatDateTime('2026-11-24T18:57:00Z');
    expect(stamp).toMatch(/^Nov 24, 2026, \d{1,2}:57 (AM|PM) \S+$/);
    expect(stamp).not.toContain('00:00:00');
    expect(utcText('2026-11-24T18:57:00.123Z')).toBe('2026-11-24 18:57:00 UTC');
  });

  it('shows an exclusive window end as the last included day', () => {
    expect(inclusiveEnd('2026-01-01T00:00:00Z')?.toISOString()).toBe(
      '2025-12-31T00:00:00.000Z',
    );
    expect(periodLabel('2025-10-03T00:00:00Z', '2026-01-01T00:00:00Z')).toBe(
      'Oct 3 – Dec 31, 2025',
    );
    expect(periodLabel('2025-12-03T00:00:00Z', '2026-01-03T00:00:00Z')).toBe(
      'Dec 3, 2025 – Jan 2, 2026',
    );
    expect(periodLabel('2025-10-03T00:00:00Z', '2025-12-31T00:00:00Z')).toBe(
      'Oct 3 – Dec 30, 2025',
    );
  });

  it('uses relative time for recent events', () => {
    const now = Date.parse('2026-11-25T12:00:00Z');
    expect(relativeTime('2026-11-25T11:59:30Z', now)).toBe('just now');
    expect(relativeTime('2026-11-25T11:55:00Z', now)).toBe('5 min ago');
    expect(relativeTime('2026-11-25T10:00:00Z', now)).toBe('2 h ago');
    expect(relativeTime('2026-11-22T12:00:00Z', now)).toBe('3 d ago');
    expect(relativeTime('2026-01-01T00:00:00Z', now)).toBe('Jan 1, 2026');
  });
});

describe('scores and identifiers', () => {
  it('formats percentages and contributions with 1 decimal', () => {
    expect(scorePercent(0.0096)).toBe('1.0%');
    expect(scorePercent(0.0089)).toBe('0.9%');
    expect(scorePercent(0.649)).toBe('64.9%');
    expect(percent1(64.904)).toBe('64.9%');
    expect(pp1(-2.139)).toBe('−2.1 pp');
    expect(pp1(1.5511)).toBe('+1.6 pp');
  });

  it('shortens identifiers to 8 characters', () => {
    expect(shortId('690505aa-1234-4000-8000-000000000000')).toBe('690505aa');
    expect(shortId('SYN-COUNTERPARTY-1a2b3c4d5e')).toBe('1a2b3c4d');
  });
});

describe('model field labels', () => {
  it('has a human label for every one of the 27 model fields', () => {
    expect(MODEL_FEATURES).toHaveLength(27);
    const missing = MODEL_FEATURES.filter((name) => !FEATURE_LABELS[name]);
    expect(missing).toEqual([]);
    for (const name of MODEL_FEATURES) {
      expect(featureLabel(name)).not.toBe(name);
      expect(findViolations(featureLabel(name))).toEqual([]);
    }
  });
});

describe('main-view guard', () => {
  it('flags raw backend output and passes formatted text', () => {
    const rules = (text: string) => findViolations(text).map((v) => v.rule);
    expect(rules('USD 72,000.00000000')).toEqual(['more_than_2_decimals']);
    expect(rules('31 CFR § 1020.320 · §  1020.210')).toEqual([]);
    expect(rules('score 0.0089')).toEqual(['more_than_2_decimals']);
    expect(rules('2025-09-23 00:00:00 UTC')).toEqual(['midnight_time']);
    expect(rules('a'.repeat(64))).toEqual(['sha256']);
    expect(rules('690505aa-1234-4000-8000-000000000000')).toEqual(['uuid']);
    expect(rules('driver nbrPaymentsCashLike90d')).toEqual([
      'model_field_name',
    ]);
    expect(rules('Human review required.')).toEqual([
      'disclaimer_outside_footer',
    ]);
    expect(
      rules(
        '$72,000 · Sep 23, 2025 · Case 690505aa · Cash-like payments · 90 days · 1.0%',
      ),
    ).toEqual([]);
  });
});
