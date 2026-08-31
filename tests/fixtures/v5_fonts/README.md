# V5 font technical fixture

`Geist-Regular.ttf` is a technical-only fixture copied from the repository-pinned
Next.js dependency tree. It is not a live AssetVersion or production-selected font.

- Marker: `TECHNICAL_FIXTURE_ONLY`
- Marker: `NOT_LIVE_ASSET`
- Marker: `NOT_SELECTED_FOR_PRODUCTION`
- Marker: `NOT_PUBLICATION_ASSET`
- Font SHA-256: `bde046ddd9f20be35b0bd56cc79eb752b967fb6661a3fe76cb067bb09f871d76`
- License: `OFL-1.1`
- License text SHA-256: `942560b236adfa83745b2c64e5fc09ebaf91cb331751b1157eb92187e5d6e930`
- Upstream: `vercel/geist-font`

The production builder must reject these markers. Tests perform representative
admission only in an isolated evidence journal with explicit digest-pinned authorities.

`ACS-Technical-CJK.ttf` is an OFL-1.1 derivative of the same pinned Geist
fixture. It adds four original geometric technical glyph outlines solely so
M13-E3 can prove exact-font Chinese layout without a system or network fallback:
`长` (U+957F), `安` (U+5B89), `名` (U+540D), and `牌` (U+724C).

- Marker: `TECHNICAL_FIXTURE_ONLY`
- Marker: `NOT_LIVE_ASSET`
- Marker: `NOT_ADMITTED`
- Marker: `NOT_MASTER`
- Marker: `NOT_SELECTED_FOR_PRODUCTION`
- Marker: `NOT_PUBLICATION_ASSET`
- Font SHA-256: `5ba77575dfda17cf164a078f5ffdeeb73e427650cb2d9b0fd9b74f51f169da4f`
- License: `OFL-1.1` (the adjacent `OFL.txt`)
- Production dependency on FontTools: `false`

The derivative was produced once as a repository fixture. FontTools is not
imported or required by any production module, and production builders must
reject every marker above.
