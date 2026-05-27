import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    outDir: resolve(__dirname, 'static/dist'),
    emptyOutDir: true,
    lib: {
      entry: resolve(__dirname, 'static/src/dashboard.ts'),
      name: 'Dashboard',
      fileName: () => 'dashboard.js',
      formats: ['iife']
    }
  }
});
