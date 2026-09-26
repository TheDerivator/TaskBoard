# Vendored third-party files

Shipped with the app so that nothing is loaded from external providers at runtime.
Wired together by the import map in `taskboard/static/index.html`.

| Path | Package | Version | License | Source file |
|---|---|---|---|---|
| `preact/preact.module.js` | preact | 10.29.8 | MIT (`preact/LICENSE`) | `dist/preact.module.js` |
| `preact/hooks.module.js` | preact | 10.29.8 | MIT | `hooks/dist/hooks.module.js` |
| `htm/htm.module.js` | htm | 3.1.1 | Apache-2.0 (`htm/LICENSE`) | `dist/htm.module.js` |
| `../fonts/*.woff2` | @fontsource/ibm-plex-sans, @fontsource/ibm-plex-mono | 5.3.0 | SIL OFL 1.1 (`../fonts/LICENSE-OFL.txt`) | `files/ibm-plex-*-latin{,-ext}-*.woff2` |

To update: `npm pack <package>@<version>` in a scratch folder, extract, copy the files listed
above, update this table, run the browser tests.
