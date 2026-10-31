export type User = { id: string; username: string; role: 'analyst' | 'admin' };

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, {
    ...init,
    cache: 'no-store',
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? 'Sign-in failed or your session expired.'
        : `Service request failed (${response.status}).`,
    );
  }
  return response.json();
}

export async function health(): Promise<boolean> {
  const result = await request('/health');
  return (
    typeof result === 'object' &&
    result !== null &&
    'status' in result &&
    result.status === 'ok'
  );
}

export async function signIn(
  username: string,
  password: string,
): Promise<string> {
  const result = await request('/api/v1/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (
    typeof result !== 'object' ||
    result === null ||
    !('access_token' in result) ||
    typeof result.access_token !== 'string'
  ) {
    throw new Error('Invalid authentication response.');
  }
  return result.access_token;
}

export async function currentUser(token: string): Promise<User> {
  const result = await request('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (
    typeof result !== 'object' ||
    result === null ||
    !('id' in result) ||
    typeof result.id !== 'string' ||
    !('username' in result) ||
    typeof result.username !== 'string' ||
    !('role' in result) ||
    !['analyst', 'admin'].includes(String(result.role))
  ) {
    throw new Error('Invalid account response.');
  }
  return result as User;
}
