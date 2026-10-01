# Lumina Design System

How Lumina looks, and why. The source of truth is `frontend/src/styles/globals.css` (tokens) and
`frontend/src/components/ui/` (primitives); this page explains them. The system follows the project's design
brief: an editorial, enterprise look with a white canvas, near-black type and pill buttons,
deep-green and navy bands for product moments, coral only for taxonomy, and blue only for links.

## Principles

1. **Flat.** Depth comes from hairline rules, radius and a change of surface — never drop shadows or
   gradients.
2. **Colour means something.** Near-black carries actions. Deep green frames product moments (the
   Admin figures). Coral marks *kinds* of things (document types, example categories) and things that
   need attention. Blue is for links. Everything else is ink on white.
3. **Tables before boxes.** Records are rule-separated rows with mono column labels (research-table
   style), not stacks of cards. Cards appear only where a record has parts to compare (a version, a
   conflict, a feedback report).
4. **One job per page.** Every page starts with the same header: mono eyebrow (its section), a large
   display title, one sentence saying what the page is for, and the page's actions on the right.
5. **Accessible by default.** AA text contrast, visible focus rings, 36–44 px hit areas, a skip link,
   keyboard-reachable everything, and no information carried by colour alone.

## Colour

| Token | Hex | Used for |
|---|---|---|
| `primary` | `#17171c` | Primary pill buttons, active tabs, dark panels (sign-in card, dark footer) |
| `primary-hover` | `#2c2c34` | Hover on primary |
| `black` | `#000000` | Announcement bar |
| `green` | `#003c33` | Admin headline band; "approved / in force" text |
| `navy` | `#071829` | Alternative dark band |
| `blue` | `#1863dc` | Links; chart series 1 |
| `coral` / `coral-soft` / `coral-ink` | `#ff7759` / `#ffad9b` / `#9c2f14` | Taxonomy chips, "needs attention" badges, chart series 2; `coral-ink` is the readable coral for text |
| `canvas` | `#ffffff` | Page background |
| `stone` / `stone-hover` | `#eeece7` / `#e4e1da` | Warm blocks: key-value cards, empty states, conflict sides, trace panels |
| `green-wash`, `blue-wash`, `coral-wash`, `error-wash` | pale tints | Status notices (chain intact, amended, warnings, errors) |
| `ink` | `#212121` | Body text |
| `muted` / `muted-dark` | `#6c6c7c` / `#93939f` | Metadata on light / dark surfaces |
| `hairline` / `border-light` / `card-border` | `#d9d9dd` / `#e5e7eb` / `#f2f2f2` | Rules, chart gridlines, the palest card edge |
| `focus` | `#4c6ee6` | Keyboard focus ring |
| `input-focus` | `#9b60aa` | Focused text field border |
| `error` | `#b30000` | Errors, overdue dates, destructive actions |

Hard-coded colours are not allowed in components; add a token instead.

## Type

| Role | Family | Utility | Size |
|---|---|---|---|
| Hero (sign-in headline) | Space Grotesk | `text-hero` | 44 → 96 px, line-height 1, −2 % tracking |
| Page title | Space Grotesk | `text-display` | 40 → 72 px, line-height 1 |
| Section heading | Inter | `text-section`, `text-card-heading` | 32 → 48 px, 24 → 32 px |
| Feature / card title | Inter | `text-feature` | 24 px |
| Lead paragraph | Inter | `text-lead` | 18 px |
| Body | Inter | (default) | 16 px, line-height 1.5 |
| Caption / micro | Inter | `text-caption`, `text-micro` | 14 px, 12 px |
| System label | Space Mono | `mono-label` | 12 px uppercase — eyebrows, column heads, section titles, codes |

The fonts are self-hosted (`@fontsource`), so the app works offline and makes no third-party requests.
Space Grotesk, Inter and Space Mono are open-licence stand-ins for the proprietary faces in the brief;
swapping them means changing three `--font-*` tokens.

Big standalone numbers (Admin figures) use proportional figures; numbers in columns use `tabular-nums`.

## Shape

Radius scale: `xs` 4 px (badges, text links) · `sm` 8 px (stone blocks, notices, inputs) · `md` 16 px
(cards) · `lg` 22 px (dark panels, the Admin band) · `xl` 30 px · `pill` 32 px (buttons, tabs, filters).

## Components (`components/ui`)

| Component | Variants | Notes |
|---|---|---|
| `Button` / `ButtonLink` / `buttonClass` | `primary`, `outline`, `link`, `inverse`, `ghost`, `danger`; sizes `md`, `sm`, `icon` | Pill shape. The page's main action is `primary`; its companion is `link` (underlined text) or `outline`. `loading` shows a spinner and sets `aria-busy`. |
| `Badge` | `success`, `amber`, `danger`, `accent`, `neutral` | Status chips; always text, never colour alone. |
| `TaxonomyChip`, `MonoLabel` | `active` | Coral chip for document types; mono system label. |
| `Card`, `Band` | `default`, `stone`, `dark`, `soft`; bands `green`, `navy`, `stone`, `dark` | Flat surfaces. |
| `Table`, `Th`, `Td`, `Tr`, `RuleList` | — | Research-table rows: top rule in `primary`, hairline row rules, mono headers. |
| `Tabs`, `Segmented` | — | Pill tabs / pill filter groups; the selected pill is filled near-black. |
| `Field`, `Input`, `Select`, `Textarea` | — | Label above, hint and error wired with `aria-describedby`; purple focus border. |
| `Dialog`, `Sheet` | — | Radix-based; the sheet is a side panel on desktop and a bottom sheet on phones. |
| `EmptyState`, `ErrorNotice`, `Skeleton`, `Toast`, `Tooltip` | — | Stone empty states; red-outlined errors with `role="alert"`. |

## Page patterns (`app/layout`)

- **AppShell** — skip link → announcement bar → top navigation → page → intended-use footer (always
  visible). Each page is wrapped in an error boundary keyed by address, and in `Suspense` for code-split
  pages.
- **TopNav** — wordmark left, one pill per section in the centre (active = filled), user and **Sign
  out** right. On phones the sections move into a menu. Clinicians, who have only Ask, get no menu.
- **SectionLayout** — the second row of pill tabs for Review and Admin. Review tabs carry a count of
  waiting items (coral when non-zero).
- **Page / PageHeader / SectionTitle** — the page frame (also sets the browser-tab title "Library ·
  Lumina"), the standard header, and the mono block heading with optional right-side actions.
- **Footer** — `light` inside the app, `dark` band on the sign-in page.

## Data visualisation

The Admin page's daily chart follows a checked procedure: stacked columns (declined on the baseline,
answered or clarified above), ≤ 24 px wide with a 4 px rounded data end and a 2 px gap between
segments, hairline gridlines, clean axis ticks. The two series colours (blue `#1863dc`, coral
`#ff7759`) were run through a colour-vision validator: they stay distinct for protanopia and
deuteranopia (ΔE 27) and for normal vision (ΔE 39). Coral is below 3:1 contrast on white, so the chart
always has a legend, a per-day read-out on hover **and** keyboard (arrow keys), and a **Show as table**
view. Bar lists use a single series colour (blue) on a stone track. Chart text always uses text tokens,
never the series colour.

## Do and don't

| Do | Don't |
|---|---|
| Use tokens (`bg-stone`, `text-muted`, `border-hairline`) | Write hex values or Tailwind palette colours (`gray-500`) in components |
| Put one primary pill per surface | Put two filled buttons side by side |
| Show records as rule-separated rows | Wrap every row in its own bordered card |
| Pair colour with a word or icon | Rely on colour alone to show status |
| Use `mono-label` for system labels and column heads | Use it for sentences |
