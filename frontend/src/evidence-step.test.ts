import { describe, expect, it } from 'vitest';
import { customerMissing, kycText } from './investigation';
import type { Customer } from './investigation-api';

const customer = {
  annual_income: '72000.00000000',
  expected_activity_status: 'not_recorded',
} as Customer;

describe('Review Evidence helpers', () => {
  it('labels the KYC rating with its scale and High threshold', () => {
    expect(kycText(1)).toBe('KYC 1 (0–6 scale, High at 3+)');
  });
  it('collects missing customer fields into one line', () => {
    expect(customerMissing(customer)).toEqual(['Expected activity']);
    expect(customerMissing({ ...customer, annual_income: null })).toEqual([
      'Annual income',
      'Expected activity',
    ]);
  });
});
