// Copy the single-file build to assets/reader-app.html, where build_reader_dashboard.py reads it.
import { copyFileSync } from 'node:fs';
copyFileSync(new URL('../dist/index.html', import.meta.url), new URL('../../assets/reader-app.html', import.meta.url));
console.log('installed assets/reader-app.html');
