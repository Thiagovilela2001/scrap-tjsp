import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/tjsp': 'http://127.0.0.1:8000',
      '/saude': 'http://127.0.0.1:8000',
      '/documentos': 'http://127.0.0.1:8000',
      '/auditorias': 'http://127.0.0.1:8000',
      '/buscar': 'http://127.0.0.1:8000',
      '/perguntar': 'http://127.0.0.1:8000',
      '/pesquisa-assistida': 'http://127.0.0.1:8000',
      '/tribunais': 'http://127.0.0.1:8000',
    },
  },
});
