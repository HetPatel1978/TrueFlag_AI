import { ApiError, request, type User } from './api';

// Only a non-secret sign-out intent may be stored. No tokens, roles or case data.
const SIGN_OUT = 'trueflag.signout.pending';
// These untrusted claims only schedule a server check; they never grant access.
export function rememberedRenewalDelay(token: string): number | null {
  try {
    const part = token.split('.')[1];
    const claims = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
    if (
      typeof claims.sid !== 'string' ||
      !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(claims.sid) ||
      typeof claims.exp !== 'number' ||
      !Number.isFinite(claims.exp)
    )
      return null;
    return Math.max(
      0,
      Math.min(2147483647, claims.exp * 1000 - Date.now() - 60000),
    );
  } catch {
    return null;
  }
}
function pending(): boolean {
  try {
    return sessionStorage.getItem(SIGN_OUT) === '1';
  } catch {
    return false;
  }
}
export function clearSignOutIntent() {
  try {
    sessionStorage.removeItem(SIGN_OUT);
  } catch {
    /* Storage may be disabled. */
  }
}
export function markSignOutIntent() {
  try {
    sessionStorage.setItem(SIGN_OUT, '1');
  } catch {
    /* No credential is stored. */
  }
}
export async function endBrowserSession() {
  markSignOutIntent();
  await request('/api/v1/auth/session/logout', {
    method: 'POST',
    credentials: 'same-origin',
  });
  clearSignOutIntent();
}
export async function restoreBrowserSession(
  signal: AbortSignal,
): Promise<{ token: string; user: User } | null> {
  if (pending()) {
    await endBrowserSession();
    return null;
  }
  try {
    const value = await request<{ access_token: string; user: User }>(
      '/api/v1/auth/session',
      { credentials: 'same-origin', signal },
    );
    if (
      !value ||
      typeof value.access_token !== 'string' ||
      !value.access_token ||
      value.access_token.length > 4096 ||
      !value.user ||
      typeof value.user.id !== 'string' ||
      typeof value.user.username !== 'string' ||
      !['analyst', 'supervisor', 'admin'].includes(value.user.role)
    )
      throw new Error('Invalid session response');
    return { token: value.access_token, user: value.user };
  } catch (failure) {
    if (failure instanceof ApiError && failure.status === 401) return null;
    throw failure;
  }
}
