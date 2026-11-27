// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, protectedRead } from './api';
import { investigationClient } from './investigation-api';

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it('honors server backpressure once and returns only a freshly authorized read', async () => {
  vi.useFakeTimers();
  const read = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(429, 3))
    .mockResolvedValue('current');
  const result = protectedRead(read);
  await vi.advanceTimersByTimeAsync(2999);
  expect(read).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(await result).toBe('current');
  expect(read).toHaveBeenCalledTimes(2);
});
it.each([401, 403, 404, 409, 503])(
  'never retries authorization, stale-evidence or clock denial %s',
  async (status) => {
    const read = vi.fn().mockRejectedValue(new ApiError(status));
    await expect(protectedRead(read)).rejects.toMatchObject({ status });
    expect(read).toHaveBeenCalledTimes(1);
  },
);
it('stops when a scope is revoked during the backoff', async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const read = vi.fn().mockRejectedValue(new ApiError(429, 10));
  const result = protectedRead(read, controller.signal);
  const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
  await vi.advanceTimersByTimeAsync(1);
  controller.abort();
  await rejected;
  expect(read).toHaveBeenCalledTimes(1);
});
it('does not retry excessive delays or repeated saturation', async () => {
  const read = vi.fn().mockRejectedValue(new ApiError(429, 61));
  await expect(protectedRead(read)).rejects.toMatchObject({ status: 429 });
  expect(read).toHaveBeenCalledTimes(1);
  vi.useFakeTimers();
  read.mockRejectedValue(new ApiError(429, 0));
  const result = protectedRead(read);
  const rejected = expect(result).rejects.toMatchObject({ status: 429 });
  await vi.advanceTimersByTimeAsync(2000);
  await rejected;
  expect(read).toHaveBeenCalledTimes(3);
});

it('never automatically retries an investigation job submission', async () => {
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      new Response('{}', { status: 429, headers: { 'Retry-After': '2' } }),
    );
  const client = investigationClient(
    'unit-test-token',
    new AbortController().signal,
    vi.fn(),
  );
  await expect(
    client.draftSubmit(
      'case',
      {
        investigation_run_id: 'parent',
        expected_packet_sha256: 'a'.repeat(64),
      },
      'unit-test-request',
    ),
  ).rejects.toMatchObject({ status: 429 });
  expect(fetch).toHaveBeenCalledTimes(1);
});
