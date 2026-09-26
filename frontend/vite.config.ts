import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
  server: {
    host: true, // Listen on all local IPs (required for Docker)
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true, // This forces Docker/Windows to sync file changes!
    }
  }
})