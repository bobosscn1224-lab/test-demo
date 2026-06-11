import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        timeout: 7200000,
        proxyTimeout: 7200000,
      },
    },
  },
});
