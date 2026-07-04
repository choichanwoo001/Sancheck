import { fileURLToPath } from 'node:url';
import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8001',
    changeOrigin: true,
  },
};

export default defineConfig({
  envDir: __dirname,
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    proxy: apiProxy,
  },
  preview: {
    port: 3000,
    host: true,
    proxy: apiProxy,
  },
});
