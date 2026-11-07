/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// El gateway sirve la app en /mapa y sus archivos en /recursos (en el nginx compartido /static es de Django).
export default defineConfig({
  base: '/recursos/',
  plugins: [react()],
  server: {
    // En desarrollo, las llamadas a la API van al gateway que corre en Docker
    proxy: { '/api': 'http://127.0.0.1:5050' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
});
