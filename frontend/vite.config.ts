import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Aspire injects services__api__http__0 with the actual API URL at dev time
const apiTarget =
  process.env.services__api__http__0 || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
