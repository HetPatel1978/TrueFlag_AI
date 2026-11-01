import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
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
