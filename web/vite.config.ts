import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

// One self-contained HTML: the Python builder injects the reader model into it.
export default defineConfig({
  plugins: [preact(), viteSingleFile()],
  build: { outDir: 'dist', assetsInlineLimit: 100_000_000, cssCodeSplit: false, reportCompressedSize: false },
});
