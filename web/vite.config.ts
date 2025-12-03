import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

const page = (path: string) => fileURLToPath(new URL(path, import.meta.url))

// Deep links like /app/profile must get the Mini App page, not the landing (nginx does the same).
function spaFallbacks(): Plugin {
  const apps = ['/app/', '/admin/']
  return {
    name: 'spa-fallbacks',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? '/'
        const base = apps.find((prefix) => url.startsWith(prefix))
        if (base && !url.includes('.') && req.headers.accept?.includes('text/html')) {
          req.url = `${base}index.html`
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), tailwindcss(), spaFallbacks()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5177,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8017' },
  },
  preview: { port: 5177 },
  build: {
    rollupOptions: {
      input: {
        landing: page('./index.html'),
        app: page('./app/index.html'),
        admin: page('./admin/index.html'),
      },
    },
  },
  test: {
    environment: 'jsdom',
  },
})
