import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    react({
      // React 19 specific settings
      jsxImportSource: 'react',
      babel: {
        plugins: [
          // React Compiler plugin if needed
          // ['babel-plugin-react-compiler', { target: '18' }]
        ]
      }
    })
  ],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
    // Watch options to avoid file watching issues in some environments
    watch: {
      usePolling: true,
      interval: 1000,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          axios: ['axios'],
          'react-query': ['@tanstack/react-query'],
        },
      },
    },
  },
  // Environment variable handling
  envPrefix: 'VITE_',
})