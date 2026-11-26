import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { searchForWorkspaceRoot } from 'vite';
import pkg from './package.json';

const identityPath = new URL('./release-build.json', import.meta.url);
let identity = {
  build_id: 'unknown',
  frontend_version: pkg.version,
  source_state: 'unknown',
};
if (existsSync(identityPath)) {
  try {
    const value = JSON.parse(readFileSync(identityPath, 'utf8'));
    if (
      value === null ||
      typeof value !== 'object' ||
      Array.isArray(value) ||
      Object.keys(value).sort().join(',') !==
        'build_id,frontend_version,source_state' ||
      typeof value.build_id !== 'string' ||
      !/^(unknown|[a-f0-9]{64})$/.test(value.build_id) ||
      value.frontend_version !== pkg.version ||
      !['unknown', 'clean', 'dirty'].includes(value.source_state)
    )
      throw new Error();
    identity = value;
  } catch {
    throw new Error('Release metadata invalid');
  }
}

// The native runtime links node_modules from outside the staged source. Allow only the
// font package's real directory in addition to Vite's default workspace root.
const fontPackage = new URL(
  './node_modules/@fontsource/public-sans',
  import.meta.url,
);
const fontDirectory = existsSync(fontPackage)
  ? [realpathSync(fontPackage)]
  : [];

export default defineConfig({
  define: { __TRUEFLAG_BUILD__: JSON.stringify(identity) },
  plugins: [react()],
  server: {
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), ...fontDirectory] },
    proxy: {
      '/api': process.env.TRUEFLAG_API_PROXY ?? 'http://127.0.0.1:8010',
      '/health': process.env.TRUEFLAG_API_PROXY ?? 'http://127.0.0.1:8010',
      '/ready': process.env.TRUEFLAG_API_PROXY ?? 'http://127.0.0.1:8010',
    },
  },
  test: {
    environment: 'node',
    clearMocks: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
