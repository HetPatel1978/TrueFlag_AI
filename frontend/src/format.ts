/**
 * Display-only formatting shared by every page. Values from the server are never changed;
 * exact values stay available in each page's Audit details.
 */

const DECIMAL = /^([+-])?(\d+)(?:\.(\d+))?$/;

/** Round an exact decimal string half away from zero, without floating point. */
export function roundDecimal(value: string, places: number): string {
  const match = DECIMAL.exec(value.trim());
  if (!match) return value;
  const [, sign, whole, fraction = ''] = match;
  const digits = BigInt(
    whole + fraction.padEnd(places + 1, '0').slice(0, places + 1),
  );
  let rounded = digits / 10n;
  if (digits % 10n >= 5n) rounded += 1n;
  const text = rounded.toString().padStart(places + 1, '0');
  const integer = places ? text.slice(0, -places) : text;
  const decimals = places ? text.slice(-places) : '';
  const negative = sign === '-' && /[1-9]/.test(text);
  return `${negative ? '-' : ''}${integer}${decimals ? '.' + decimals : ''}`;
}

function decimalText(value: string | number): string {
  if (typeof value === 'string') return value.trim();
  if (!Number.isFinite(value)) return String(value);
  return Math.abs(value) < 1e-6 && value !== 0
    ? value.toFixed(12)
    : String(value);
}

const symbols = new Map<string, string>();
function currencySymbol(currency: string): string {
  if (!symbols.has(currency)) {
    let symbol = `${currency} `;
    try {
      const part = new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency,
      })
        .formatToParts(0)
        .find((p) => p.type === 'currency')?.value;
      if (part)
        symbol = part.length > 1 && /^[A-Z]{3}$/.test(part) ? `${part} ` : part;
    } catch {
      /* unknown code: keep the code itself */
    }
    symbols.set(currency, symbol);
  }
  return symbols.get(currency)!;
}

const group = (digits: string) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');

/**
 * "$1,234.57". `whole` for declared whole amounts (income, limits): 0 decimals.
 * `signed` prefixes "+" for positive values (net flows). Never more than 2 decimals.
 */
export function money(
  value: string | number | null | undefined,
  currency: string | null | undefined,
  options: { whole?: boolean; signed?: boolean } = {},
): string {
  if (value === null || value === undefined || value === '')
    return 'Not available';
  const text = decimalText(value);
  if (!DECIMAL.test(text)) return currency ? `${currency} ${text}` : text;
  const rounded = roundDecimal(text, options.whole ? 0 : 2);
  const negative = rounded.startsWith('-');
  const [integer, decimals] = rounded.replace('-', '').split('.');
  const amount = `${currency ? currencySymbol(currency) : ''}${group(integer)}${decimals ? '.' + decimals : ''}`;
  if (negative) return `−${amount}`;
  return options.signed && /[1-9]/.test(rounded) ? `+${amount}` : amount;
}

/** Subtract two exact decimal strings (a − b), keeping scale. */
export function subtractDecimal(a: string, b: string): string {
  const scale = Math.max(
    (a.split('.')[1] ?? '').length,
    (b.split('.')[1] ?? '').length,
  );
  const toUnits = (v: string) => {
    const [i, f = ''] = v.replace('-', '').split('.');
    const units = BigInt(i + f.padEnd(scale, '0'));
    return v.trim().startsWith('-') ? -units : units;
  };
  const diff = toUnits(a) - toUnits(b);
  const abs = (diff < 0n ? -diff : diff).toString().padStart(scale + 1, '0');
  const body = scale ? `${abs.slice(0, -scale)}.${abs.slice(-scale)}` : abs;
  return diff < 0n ? `-${body}` : body;
}

// ---- dates and times ---------------------------------------------------------------------

const DAY = 86_400_000;

function parse(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** True when a timestamp carries no time of day (exactly 00:00:00 UTC). */
export function isDateOnly(value: string | Date): boolean {
  const date = parse(value);
  return (
    !!date &&
    date.getUTCHours() === 0 &&
    date.getUTCMinutes() === 0 &&
    date.getUTCSeconds() === 0 &&
    date.getUTCMilliseconds() === 0
  );
}

/** "Sep 23, 2025". Date-only values are read in UTC so the calendar day never shifts. */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return 'Not available';
  const date = parse(value);
  if (!date) return String(value);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: isDateOnly(date) ? 'UTC' : undefined,
  });
}

/** "Nov 24, 2026, 1:57 PM EST" in the viewer's zone; date only when the time is 00:00:00. */
export function formatDateTime(
  value: string | Date | null | undefined,
): string {
  if (!value) return 'Not available';
  const date = parse(value);
  if (!date) return String(value);
  if (isDateOnly(date)) return formatDate(date);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

/** Exact UTC value for tooltips and Audit details. */
export function utcText(value: string | Date | null | undefined): string {
  if (!value) return '';
  const date = parse(value);
  return date
    ? date
        .toISOString()
        .replace('T', ' ')
        .replace(/\.\d{3}Z$/, ' UTC')
    : String(value);
}

/** "just now", "5 min ago", "2 h ago", "3 d ago"; older than 30 days → the date. */
/** Exact local time with seconds and time zone, e.g. for the tooltip on a relative time. */
export function exactLocalTime(
  value: string | Date | null | undefined,
): string {
  if (!value) return 'Not available';
  const date = parse(value);
  if (!date) return String(value);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  });
}

export function relativeTime(
  value: string | Date | null | undefined,
  now = Date.now(),
): string {
  if (!value) return 'Not available';
  const date = parse(value);
  if (!date) return String(value);
  const seconds = Math.round((now - date.getTime()) / 1000);
  if (seconds < 0) return formatDateTime(date);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < DAY / 1000) return `${Math.floor(seconds / 3600)} h ago`;
  if (seconds < 30 * (DAY / 1000))
    return `${Math.floor(seconds / (DAY / 1000))} d ago`;
  return formatDate(date);
}

/** An exclusive window end (midnight) shown as the last included day. */
export function inclusiveEnd(end: string | Date): Date | null {
  const date = parse(end);
  if (!date) return null;
  return isDateOnly(date) ? new Date(date.getTime() - DAY) : date;
}

/** "Oct 3 – Dec 31, 2025" for a [start, end) window. */
export function periodLabel(start: string | Date, end: string | Date): string {
  const from = parse(start);
  const to = inclusiveEnd(end);
  if (!from || !to) return `${String(start)} – ${String(end)}`;
  const utc = isDateOnly(from) ? 'UTC' : undefined;
  const sameYear = from.getUTCFullYear() === to.getUTCFullYear();
  const first = from.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
    timeZone: utc,
  });
  return `${first} – ${formatDate(to)}`;
}

// ---- numbers, scores and identifiers -------------------------------------------------------

/** A model score in 0..1 as a percentage with 1 decimal: 0.0096 → "1.0%". */
export function scorePercent(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score))
    return 'Not available';
  return `${(Math.round(score * 1000) / 10).toFixed(1)}%`;
}

/** A value already in percent with 1 decimal: 64.904 → "64.9%". */
export function percent1(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '')
    return 'Not available';
  const number = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(number)) return String(value);
  return `${number.toFixed(1)}%`;
}

/** Percentage points with sign and 1 decimal: −2.139 → "−2.1 pp". */
export function pp1(value: number | string): string {
  const number = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(number)) return String(value);
  const text = Math.abs(number).toFixed(1);
  if (text === '0.0') return '0.0 pp';
  return `${number < 0 ? '−' : '+'}${text} pp`;
}

/** First 8 characters of an identifier for the main view; the full value is in Audit details. */
export function shortId(value: string | null | undefined): string {
  return value ? value.replace(/^[A-Z]+-[A-Z]+-/, '').slice(0, 8) : '';
}
