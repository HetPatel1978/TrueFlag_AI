import { createContext } from 'react';
import type { Submission } from './api';

export type Receipt = { body: Submission; key: string };
// Session-only uncertain submissions survive view changes; logout discards the provider.
export const Receipts = createContext<Map<string, Receipt> | null>(null);
