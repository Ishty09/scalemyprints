# @scalemyprints/extension

Chrome (and Firefox) extension that adds a one-click trademark risk check to Etsy, Amazon, and Redbubble listing pages.

## Architecture

```
src/
├── background/        Service worker — owns API calls + chrome.storage
├── content/           Injected into listing pages via Manifest V3 content_scripts
├── popup/             Toolbar popup (plain DOM, no React)
└── shared/            Types, config, storage helpers used across contexts
public/
├── manifest.json      Manifest V3 declaration
├── icons/             Toolbar icons (16/32/48/128)
└── content.css        Required by manifest; actual styles live in Shadow DOM
```

## Build

```bash
pnpm install
pnpm build           # → dist/
pnpm build:zip       # → scalemyprints-extension.zip (ready for Chrome Web Store)
```

## Local development

```bash
pnpm dev             # rebuilds dist/ on every change
```

Then in Chrome:

1. Visit `chrome://extensions`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select `dist/`

When you change source files, Vite rebuilds `dist/`. You then need to click the refresh icon on the extension card in `chrome://extensions` once per change.

## How the widget works

1. The content script runs on all listing-page URL patterns declared in `manifest.json`
2. It calls `detectListing()` which inspects platform-specific selectors to extract the title
3. If a listing is detected, a small Shadow-DOM widget is injected at bottom-right
4. Click "Check trademark risk" → message goes to background worker
5. Background worker hits the API (avoids CORS), records usage, and caches the result
6. Result renders inline with risk score, per-jurisdiction breakdown, and signup CTA

## Free tier limits

- **5 anonymous searches per day** per browser, tracked in `chrome.storage.local`
- After hitting the cap, the widget shows a "Sign up" CTA instead of running the search
- Cached results don't count against the daily quota

## Publishing to Chrome Web Store

1. `pnpm build:zip` to produce `scalemyprints-extension.zip`
2. Visit https://chrome.google.com/webstore/devconsole
3. New item → upload the ZIP
4. Fill in the listing fields (description, screenshots, privacy practices)
5. Submit for review (typically 2–7 days)

## Testing checklist before publishing

- [ ] Etsy listing page — widget appears, click → result
- [ ] Amazon US listing — same
- [ ] Amazon UK + AU domains — same
- [ ] Redbubble listing — same
- [ ] SPA navigation — widget rebinds when user clicks to next listing
- [ ] Quota — 6th anonymous search shows quota CTA
- [ ] Network failure — graceful error message
- [ ] Popup — toolbar icon shows usage stats
- [ ] Style isolation — host page CSS doesn't leak into widget
