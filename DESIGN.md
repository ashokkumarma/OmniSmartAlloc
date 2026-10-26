# OmniSmartAlloc design brief

## Product
**Who:** an operations lead at a seller on four channels (DTC, Amazon, Etsy, Walmart) who shares one warehouse across them.
**Job:** decide how many units each channel may sell, and approve the agent's risky moves with confidence.
**One line:** one stock pool, four channels, allocated by an agent that reads every system through Zetaris.

### Routes and flows (unchanged URLs)
| Route | Purpose |
|---|---|
| `/` (`/ops`) | Overview: what needs attention, stock health, recent orders, live agent run |
| `/orders` | One queue for all orders: filter, search, fulfil, split, cancel |
| `/inventory`, `/inventory/<SKU>` | Stock, channel caps, inbound; one SKU in detail |
| `/agent` | How channels are ranked, every decision with its maths, approve or deny |
| `/storefronts` (`/channels`) | Place test orders as a shopper on each channel |
| `/sources` | The systems behind the numbers and the live federated query |
| `/classic/*` | The previous pages, kept as a fallback |

### Where a new user gets lost, and the fix
- Before: two separate pages with different headers; first value needed a click on Reset, then Run. Now the Overview opens with a first-run panel that loads demo data in one click and then offers the agent run.
- Clicks from landing to first real value: 1 (Overview shows the numbers) and 2 to a first agent run.

## Design system (revamp v2)

The three products share one foundation, defined once in each app's `src/foundation.css`. Components use the names in the app stylesheet, and each of those points at a foundation token, so no component holds a raw colour, size or duration.

- **Source.** DESIGN_REFERENCE.md (a measured study of two institutional sites). The system is replicated, not their content, logos or licensed fonts.
- **Gray ramp.** `#000`, `#06080C`, `#111`, `#1F1F1F`, `#282828`, `#595959`, `#969696`, `#A3A3A3`, `#D9D9D9`, `#F2F2F2`; paper `#F2EDE6`.
- **Themes.** Dark is the base: black page, `#111` / `#1F1F1F` / `#282828` surfaces, `#969696` secondary text, translucent nav `rgba(22,22,23,0.8)`. Light is tuned separately: paper page, white surfaces, ink text, `#595959` secondary text, `#D9D9D9` lines. **Auto** follows the OS; **Light** and **Dark** override it and are kept in the browser (`data-theme` on `<html>`).
- **Type.** Inter Variable for everything. Display 72/72, title 32/1.1, both at weight 400 with -0.03em tracking; eyebrow 14px uppercase +0.12em at 500; body 16/24; button 15/20 +0.3px at 600. Weight is kept for buttons and small labels. SQL and run output use the system monospace.
- **Space and shape.** Sections 128 by 80 px (64 by 20 on phones), 1440 px container. Radius 8 px for buttons and inputs, 100 px pills, 6 px small cards, 20 px large panels; 1 px lines instead of shadows.
- **Breakpoints.** 375 (base), 768, 1009, 1440.
- **States.** Hover moves secondary text to primary in 150 ms; numbered rows shift 8 px and show an arrow; focus is a 2 px accent ring with a 2 px offset; disabled is 45% opacity; loading keeps the button width.
- **Motion tokens.** `--ds-ease-out` cubic-bezier(0.16, 1, 0.3, 1) for section entry (600 ms, once); `--ds-ease-app` cubic-bezier(0.2, 0, 0.2, 1) for app transitions (150 to 250 ms); the cycling word swaps in 350 ms every 2.8 s. Only transform and opacity animate. Reduced motion turns all of it off.

### Landing page (`/`)

The app moved to `/app`; every other URL is unchanged. The landing page follows one order: floating nav, hero, trust strip of real facts, five numbered capabilities, one pinned paper section with a word-by-word reveal, three product pillars with a live preview, closing line and footer. Scrolling uses Lenis (`lenis`, about 3 kB) for smooth, inertial scrolling on the landing page only; it turns itself off for reduced motion and is removed when you open the app. A canvas draws the hero object; everything else is CSS transitions driven by small scroll handlers. As the story section arrives the whole page blends from the theme colours to paper (ink in the light theme) and back, so sections change without hard edges, and the five capability rows fade up one after another.

- **Hero object.** It sits in the right track of the hero grid, centred on the headline, and shares its left edge with the statement and buttons; its edges fade out. A point cloud with perspective, depth fade and back-to-front drawing, on a dark disc with an accent rim light. It turns slowly, tilts toward the pointer, and drifts and fades as the hero scrolls away. It draws one still frame when reduced motion is on or the device is low power, and stops while off screen or in a hidden tab.
- **Copy rules.** Each headline says what the product does; facts and figures come from the product and its demo data; no testimonials, logos or invented metrics.

### OmniSmartAlloc

- **Accent.** Teal `#0E7C9E` (fills, white label), `#4CC9EE` as text on dark, `#0A6580` on paper. Cool and operational, and clear of the four channel colours; Walmart now uses its own blue.
- **Hero object.** An orbit: a sphere of points (the stock pool) circled by one tilted ring per channel. The lit arc on each ring is that channel's share of the caps, read from the first SKU that has an allocation, and a unit travels along each lit arc.
- **Cycling word.** Read, Rank, Supply: three things the product really does.
