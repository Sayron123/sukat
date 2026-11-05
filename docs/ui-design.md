# UI design update — What and why

The web app now follows the Figma design ("Hardware Store Inventory App"). Only screens that already exist were changed. Screens from later phases (AI chat, sales dashboard, staff invite) are not built yet.

## Step 1 — Design parts and app shell

**What**
- `web/src/app/globals.css` — colors from the design (`line` for input borders, `subtle` for hints, `dark` for the camera screen).
- `web/src/components/icons.tsx` — the design's line icons (home, box, camera, receipt, …).
- `web/src/components/ui.tsx` — Button (56px main button), outlined button, Field (bold label, 48px box, optional ₱ prefix / unit suffix / hint), Select, SearchBox, Chip (dark when selected), Badge (red / amber / green / grey), Card, Notice (grey info box), Avatar, Pager, Loading.
- `web/src/components/app-nav.tsx` — bottom tab bar: **Home, Stock, AI, More**. AI is shown greyed out until its phase.
- `web/src/components/page-header.tsx` — sticky header: small uppercase line, bold title, back arrow, right-side action.
- `web/src/components/action-dock.tsx` — the main button fixed at the bottom of the screen ("Scan Stock In", "Save Product", …), above the tabs when the page has them.
- `web/src/components/app-page.tsx` — `<AppPage tab="stock">` shows the tabs; without `tab`, the page is a sub-screen with a back arrow.

**Why**
- One set of parts means every screen looks the same and a design change is made in one place.
- The main action is always in the same spot, at thumb reach.

## Step 2 — Screens

| Screen | Change |
|---|---|
| Login / Sign up | "Welcome back" / "Set up your store", button fixed at the bottom. After login you land on Home. |
| Home (`/`) | Now a signed-in screen: today's date, store name, recent activity (last 5 sales and stock-ins), **Scan Receipt** button. |
| Stock | "N products", search box, category chips, one card per product with a red **Low** badge and big stock number, **Scan Stock In** button. **+** opens Add product. |
| Add / Edit product | Design form: Product name, Category, Base unit, Selling price (₱), Low stock alert (with unit). Extra fields kept: In stock, Other names, Other units. Archive at the bottom. |
| Import starter items | Grouped list with checkboxes, **Import N items** button at the bottom. |
| More (new, `/more`) | Store and user, links to History, Staff, Add product, Import, and **Sign out**. Add product / Import are shown to managers and secretaries only. |
| Staff | Avatar, name, email, role badge; "Roles control access" note. |
| Scan (stock in and sale) | Dark camera screen: close, gallery, big round shutter, switch between stock in and sale. |
| Review | "N items found", "Check highlighted items" note, one card per line with **Qty / Unit / Price / Total**, amber left edge for lines to check, total row, **Save Stock In** / **Save Sale**. |
| History, transaction detail | Rows with type badges, short dates ("Today, 10:32 AM"), void button on the detail. |

**Why**
- Staff and History moved under **More** so the tab bar has only the four main places, as in the design.
- The camera button still opens the phone's own camera app. A live in-page camera would need more work and permissions; the phone's camera is faster and more reliable on cheap Android phones.

## Not changed
- No API changes. All tests pass as before.
- No new features: staff invite, sales dashboard numbers and the AI tab come in their own phases.
