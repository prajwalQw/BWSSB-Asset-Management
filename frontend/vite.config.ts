import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rolldownOptions: {
      external: ['zod', 'apache-arrow'],
    },
  },
  server: {
    port: 5180,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 0,
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            // Gracefully handle backend connection blips without leaking sockets
            if (res && 'writeHead' in res && !(res as any).headersSent) {
              try {
                (res as any).writeHead(503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Backend temporarily unavailable', message: err.message }));
              } catch {
                // ignore
              }
            }
          });
        },
      },
    },
  },
});
