# UI design update — What and why

The web app now follows the Figma design ("Hardware Store Inventory App").

## Step 1 — Design parts and app shell

**What**
- `web/src/app/globals.css` — colors from the design (`line` for input borders, `subtle` for hints, `dark` for the camera screen).
- `web/src/components/icons.tsx` — the design's line icons (home, box, camera, receipt, …).
- `web/src/components/ui.tsx` — Button (56px main button), outlined button, Field (bold label, 48px box, optional ₱ prefix / unit suffix / hint), Select, SearchBox, Chip (dark when selected), Badge (red / amber / green / grey), Card, Notice (grey info box), Avatar, Pager, Loading.
- `web/src/components/app-nav.tsx` — bottom tab bar: **Home, Stock, AI, More**.
- `web/src/components/page-header.tsx` — sticky header: small uppercase line, bold title, back arrow, right-side action.
- `web/src/components/action-dock.tsx` — the main button fixed at the bottom of the screen ("Scan Stock In", "Save Product", …), above the tabs when the page has them.
- `web/src/components/app-page.tsx` — `<AppPage tab="stock">` shows the tabs; without `tab`, the page is a sub-screen with a back arrow.

**Why**
- One set of parts means every screen looks the same and a design change is made in one place.
- The main action is always in the same spot, at thumb reach.

## Step 2 — Screens

| Screen | Change |
|---|---|
| Login / Sign up | "Sign in" / "Set up your store", button fixed at the bottom. Password fields have a show/hide eye. Sign up and Forgot password have a back arrow. After login you land on Home. |
| Joining a store | Sign up first asks **Manager** or **Member**. Manager goes to Set up your store. Member pastes an invite link. `/invite` shows the role from the link. A new person sets a password with the live rules list and can ask for a suggested one. Someone with an account enters their password. Managers create links on Staff by choosing Secretary or Member. |
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
