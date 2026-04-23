# geo-mcp logo — handoff

## Files
- `geo-mcp-mark.svg` — the mark only, 120×120 viewBox, crops cleanly to any size
- `geo-mcp-mark-mono.svg` — monochrome ink version (no accent colour) for favicons, single-colour contexts

## Tokens
- Ink: `#0f1419`
- Cream background: `#f5f1e8`
- Warm accent (centre dot + ring): `#b5603a` — from `oklch(0.55 0.15 40)`
- Wordmark: Inter, weight 600, letter-spacing `-0.02em`, lowercase `geo-mcp`
- Technical/mono labels: JetBrains Mono, uppercase, 0.1–0.14em tracking

## Lockup rules
- Horizontal lockup: mark height ≈ 1.33× wordmark cap height, gap = wordmark x-height × 1.5
- Minimum clear space around mark = one grid cell (≈ 25% of mark width)
- Favicon: mark scales down cleanly to 16px; at that size the inner rings collapse — use `geo-mcp-mark-mono.svg` with no accent fill.

## Don'ts
- Don't rotate the tile
- Don't recolour the accent away from the warm-stamp hue (it references attribution/licence stamps)
- Don't stretch — always preserve aspect ratio
