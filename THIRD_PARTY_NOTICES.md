# Third-party notices

OmniSmartAlloc's own code is MIT-licensed (see `LICENSE`). It includes or depends on the following
third-party work. Nothing here is relicensed; each component keeps its own licence.

## Included in this repository

| Component | Where | Licence | Notes |
|---|---|---|---|
| Chart.js v4.4.1 (bundles @kurkle/color v0.3.2) | `demo/web/vendor/chart.umd.js` | MIT | Used by the classic `/oms` and `/ims` pages. Licence header kept in the file. |
| Meterless H-MEM conformance runner and vectors | `engines/hmem/conformance/runner.ts`, `engines/hmem/conformance/vectors/vectors.json` | Apache-2.0 | Copied unmodified from [meterless/meterless](https://github.com/meterless/meterless) at commit `1742dec` (`engines/hmem/conformance`). Full licence text: `engines/hmem/conformance/LICENSE`. |
| H-MEM engine | `engines/hmem/src/` | MIT (this repo) | Written by the team during the event to the Meterless H-MEM spec (Apache-2.0, meterless/meterless `engines/hmem/AGENTS.md`); first built for the team's other entry and adapted here. See README, "Pre-existing components". |
| Satoshi variable font | `demo/app/src/fonts/` | Fontshare Free Font Licence (free for commercial use) | Self-hosted by the React app. |

## Not included (installed or downloaded separately)

| Component | Licence | How it is obtained |
|---|---|---|
| Zetaris Lightning platform bundle and JDBC driver (`ndp-jdbc-driver-*.jar`) | Zetaris terms (hackathon materials) | Extracted to `./zetaris-platform/` (gitignored); never committed |
| Meterless Nightshift runtime | Meterless terms | Installed and run locally; the app only calls its OpenAI-compatible endpoint |
| NVIDIA Nemotron models (via Meterless Nightshift, or NVIDIA NIM as a fallback) | NVIDIA terms | Called over HTTP; no weights are included |

### Python packages (`requirements.txt`)

| Package | Licence |
|---|---|
| openai | Apache-2.0 |
| pydantic | MIT |
| python-dotenv | BSD-3-Clause |
| requests | Apache-2.0 |
| rich | MIT |
| docker | Apache-2.0 |
| JayDeBeApi | LGPL-3.0 |
| pytest | MIT |
| psycopg (binary) | LGPL-3.0 |

### npm packages (`demo/app/package.json`, versions from `package-lock.json`)

| Package | Version | Licence |
|---|---|---|
| react, react-dom | 19.3.1 | MIT |
| three | 0.170.0 | MIT |
| @react-three/fiber | 9.8.2 | MIT |
| chart.js | 4.6.1 | MIT |
| lenis | 1.3.27 | MIT |
| motion | 12.43.0 | MIT |
| lucide-react | 1.61.0 | ISC |
| vite | 8.3.5 | MIT (dev) |
| @vitejs/plugin-react | 6.1.2 | MIT (dev) |
| typescript | 6.0.3 | Apache-2.0 (dev) |
| @types/react, @types/react-dom, @types/three | | MIT (dev) |

`engines/hmem` has no npm dependencies; it runs on Node 22.18+ with built-in TypeScript type stripping.
