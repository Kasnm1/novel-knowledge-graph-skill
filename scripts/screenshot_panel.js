#!/usr/bin/env node
/**
 * Screenshot one entity panel from a built dashboard.html, so a layout change can
 * be reviewed visually instead of inferred from markup.
 *
 * Optional: requires a local Playwright install and a Chrome/Chromium binary.
 * Configure with environment variables when the defaults do not apply:
 *   PLAYWRIGHT_PATH  module path, e.g. /usr/lib/node_modules/playwright
 *   CHROME_PATH      browser binary, e.g. /usr/bin/google-chrome
 *
 * Usage:
 *   node screenshot_panel.js <dashboard.html> <entity-id> <out.png> [category]
 *
 * `category` filters to the matching category card(s); pass several separated by
 * "|" (e.g. "魂技|武魂") to capture them together. Omit it for the whole panel.
 * Prefer smoke_dashboard.py --dump-dir for structural checks: it is stdlib-only
 * and catches lost JS helpers. Use this only when the pixels matter.
 */

const path = require('path');

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_PATH, 'playwright'].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      if (error.code !== 'MODULE_NOT_FOUND') throw error;
    }
  }
  console.error('Playwright not found. Set PLAYWRIGHT_PATH to its module directory.');
  process.exit(2);
}

function loadChromePath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const guesses = [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ];
  const fs = require('fs');
  return guesses.find((guess) => fs.existsSync(guess));
}

(async () => {
  const [file, entity, out, category] = process.argv.slice(2);
  if (!file || !entity || !out) {
    console.error('usage: node screenshot_panel.js <dashboard.html> <entity-id> <out.png> [category|category]');
    process.exit(2);
  }
  const { chromium } = loadPlaywright();
  const executablePath = loadChromePath();
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 });
  page.on('pageerror', (error) => console.log('PAGEERROR:', error.message));

  // The dashboard reads the entity from the query string; the path must be
  // absolute or Chromium resolves it against the root and fails to load.
  const url = 'file:///' + path.resolve(file).replace(/\\/g, '/') + '?entity=' + encodeURIComponent(entity);
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(1200);

  if (!category) {
    await page.locator('#detail').screenshot({ path: out });
    const height = await page.evaluate(() => document.querySelector('#detail').getBoundingClientRect().height);
    console.log('panel', entity, 'height', Math.round(height), '->', out);
  } else {
    const wanted = category.split('|');
    const found = await page.evaluate((labels) => {
      const hits = [];
      for (const details of document.querySelectorAll('details.category')) {
        const title = details.querySelector('.category-title');
        const match = labels.some((label) => title && title.textContent.includes(label));
        if (match) { details.open = true; hits.push(details); } else { details.style.display = 'none'; }
      }
      if (hits.length) hits[0].scrollIntoView();
      return hits.length;
    }, wanted);
    if (!found) {
      console.error('no category matched:', category);
      await browser.close();
      process.exit(1);
    }
    await page.waitForTimeout(300);
    const box = await page.evaluate((labels) => {
      const picked = [...document.querySelectorAll('details.category')].filter((details) =>
        labels.some((label) => details.querySelector('.category-title')?.textContent.includes(label)));
      const rects = picked.map((details) => details.getBoundingClientRect());
      const left = Math.min(...rects.map((r) => r.x));
      const right = Math.max(...rects.map((r) => r.right));
      const top = Math.min(...rects.map((r) => r.y));
      const bottom = Math.max(...rects.map((r) => r.bottom));
      return { x: left, y: top, width: right - left, height: bottom - top };
    }, wanted);
    await page.screenshot({
      path: out,
      clip: { x: box.x, y: box.y, width: box.width, height: Math.min(box.height, 2400) },
    });
    console.log('category', category, 'height', Math.round(box.height), '->', out);
  }
  await browser.close();
})();
