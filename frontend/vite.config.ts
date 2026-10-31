import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8010',
      '/health': 'http://127.0.0.1:8010',
      '/ready': 'http://127.0.0.1:8010',
    },
  },
  test: { environment: 'node', clearMocks: true },
});
