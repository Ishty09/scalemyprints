import { resolve } from 'node:path'
import { defineConfig } from 'vite'

/**
 * Multi-entry Vite build for a Chrome Manifest V3 extension.
 *
 * Outputs:
 *   dist/background.js   — service worker
 *   dist/content.js      — injected on listing pages
 *   dist/popup.html      — toolbar popup
 *   dist/popup.js        — popup script
 *   dist/manifest.json   — copied verbatim from public/
 *   dist/styles.css      — content script styles
 *   dist/icon-*.png      — toolbar icons
 */
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        background: resolve(__dirname, 'src/background/index.ts'),
        content: resolve(__dirname, 'src/content/index.ts'),
        popup: resolve(__dirname, 'src/popup/index.html'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: (asset) => {
          if (asset.name?.endsWith('.css')) return '[name][extname]'
          return 'assets/[name]-[hash][extname]'
        },
      },
    },
    target: 'esnext',
    minify: 'esbuild',
    sourcemap: true,
  },
  publicDir: 'public',
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
