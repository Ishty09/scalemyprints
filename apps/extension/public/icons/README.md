# Icon placeholders

Before publishing to the Chrome Web Store you must replace these with real PNG icons:

- icon-16.png  (16×16)
- icon-32.png  (32×32)
- icon-48.png  (48×48)
- icon-128.png (128×128)

Quick way to generate from a single SVG:
```bash
# Install ImageMagick if needed: apt-get install imagemagick
convert -resize 16x16 logo.svg public/icons/icon-16.png
convert -resize 32x32 logo.svg public/icons/icon-32.png
convert -resize 48x48 logo.svg public/icons/icon-48.png
convert -resize 128x128 logo.svg public/icons/icon-128.png
```

Or use https://realfavicongenerator.net or Figma's export.

The icon should match the brand: "SMP" wordmark on a teal-to-orange gradient background, rounded square. Roughly 12-16px corner radius for the 128px version, scaled proportionally for smaller sizes.
