import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/tjsp': 'http://127.0.0.1:8000',
      '/saude': 'http://127.0.0.1:8000',
      '/documentos': 'http://127.0.0.1:8000',
      '/auditorias': 'http://127.0.0.1:8000',
      '/buscar': 'http://127.0.0.1:8000',
      '/perguntar': 'http://127.0.0.1:8000',
    },
  },
});
