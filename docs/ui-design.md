# UI design update — What and why

The web app now follows the Figma design ("Hardware Store Inventory App").

## Step 1 — Design parts and app shell

**What**
- `web/src/app/globals.css` — colors from the design and the mascot spec (`line` for input borders, `subtle` for hints, `dark` for the camera screen). Dark is the default theme; see **Mascot, theme and brand** below.
- `web/src/components/icons.tsx` — the design's line icons (home, box, camera, receipt, …).
- `web/src/components/ui.tsx` — Button (56px main button), outlined button, Field (bold label, 48px box, optional ₱ prefix / unit suffix / hint), Select, SearchBox, Chip (dark when selected), Badge (red / amber / green / grey), Card, Notice (grey info box), Avatar, Pager, Loading.
- `web/src/components/app-nav.tsx` — bottom tab bar: **Home, Stock, Ask Sukat, More**. Ask Sukat uses a one-color version of the small Sukat mark.
- `web/src/components/page-header.tsx` — sticky header: small uppercase line, bold title, back arrow, right-side action.
- `web/src/components/action-dock.tsx` — the main button fixed at the bottom of the screen ("Scan", "Save Product", …), above the tabs when the page has them.
- `web/src/components/app-page.tsx` — `<AppPage tab="stock">` shows the tabs; without `tab`, the page is a sub-screen with a back arrow.

**Why**
- One set of parts means every screen looks the same and a design change is made in one place.
- The main action is always in the same spot, at thumb reach.

## Step 2 — Screens

| Screen | Change |
|---|---|
| Login / Sign up | Sign in, Create an account (`/signup`) and Set up your store (`/signup/manager`) start with the waving Sukat, the **Sukat** wordmark and one small line under it (first field on Sign in: **Email or username**). The button is fixed at the bottom on sign-up. On login, **Sign in** comes right after the fields; when Google is set up, an "or" line and **Continue with Google** sit under it, then a "New to Sukat? **Create account**" text link. On sign-up and invites, **Continue with Google** sits at the top, then an "or" line and the form. After Google, one short page (`/google`, "Signed in with Google as …") asks only for what Google can't give: store name and address for a new store, your name (filled from Google, can be changed) for a new person, and the Terms box. The ticket from Google lasts 15 minutes. |
| Joining a store | Sign up first asks **Manager** or **Member**. Manager goes to Set up your store. Member pastes an invite link. `/invite` shows the store, the role and the invite's name. A new person picks a **username**, types their name and sets a password with the live rules list (they can ask for a suggested one). "Already have a Sukat account? Join with it" switches to email or username + password. **Continue with Google** joins with Google instead (Terms box first). Managers create links on Staff by choosing a role and an optional name; no email. |
| Home (`/`) | Now a signed-in screen: the Sukat logo at the top, then today's date, store name, recent activity (last 5 sales and stock-ins), **Scan** button. |
| Stock | "N products", search box, category chips, one card per product with a red **Low** badge and big stock number, **Scan** button. **+** opens Add product. |
| Add / Edit product | Design form: Product name, Category, Base unit, Selling price (₱), Low stock alert (with unit). Extra fields kept: In stock, Other names, Other units. Archive at the bottom. |
| Import starter items | Grouped list with checkboxes, **Import N items** button at the bottom. |
| More (new, `/more`) | Store and user with a Settings gear beside them, links to History, Staff, Add product, Import, and **Sign out**. Add product / Import are shown to managers and secretaries only. |
| Settings (`/more/settings`) | A list, no forms: **Your account** (Name, Email with a lock because it can't be changed, Password → Change, and **Google**. When Google uses the same email, the Email row shows the Google mark and the note says you can sign in either way. A different Google email gets its own Google row with that email. Not connected: a Google row with Connect, when Google is set up), **Store** (Store name, Address; only managers can open them), **Appearance** (Light / Dark / System; Dark until the person picks one), then a red **Sign out** and the app version. Name, Store and Password each open their own page (`/more/settings/name`, `/store`, `/password`) with an orange Save button and Cancel at the bottom. Saving goes back to Settings and shows a short message at the bottom. |
| Staff (`/staff`) | "N people", orange **+ Invite**, role chips, one card with every person (avatar, name with "(you)", email or @username, role badge; the owner's badge is orange). Managers tap a person to open them. **Invites not accepted yet** lists open invites by name (or "Member invite") with **Resend**, which makes a new link in a Copy/Share sheet. |
| Staff person (`/staff/[id]`) | Card with name, email or @username and the join date. **Role** as radio cards ("· current"), **Name in this store**, **Make a password reset link** (Copy/Share sheet), **Remove from store** (bottom sheet to confirm), **Save role** at the bottom. The owner and yourself can't be changed or removed. |
| Scan (stock in and sale) | Dark camera screen: close, gallery, big round shutter. The header says "Scanning: Sale" or "Scanning: Stock in". See Scan flow below. |
| Review | "N items found", a red "N lines need a double check" note, one card per line with **Qty / Unit / Price / Total**, red left edge and an **Approve** button for lines to check, total row, trash in the header (moves the photo to the Recycle bin). The title and button follow the scan's mode: **Review Stock In** with **Save Stock In**, **Review Sale** with **Save Sale**. |
| History, transaction detail | Rows with type badges, short dates ("Today, 10:32 AM"), void button on the detail. |

**Why**
- Staff and History moved under **More** so the tab bar has only the four main places, as in the design.
- The camera button still opens the phone's own camera app. A live in-page camera would need more work and permissions; the phone's camera is faster and more reliable on cheap Android phones.

## Scan flow

**What**
1. Home and Stock have the same **Scan** button (`web/src/components/scan-button.tsx`).
2. Tapping it opens a bottom sheet, "What are you scanning?" (`web/src/components/scan-mode-sheet.tsx`), with two options and Cancel:
   - **Sale / Receipt**: "Customer bought items", "Stock goes down ↓". Goes to `/scan/sale`.
   - **Stock In / Delivery**: "Items arrived from supplier", "Stock goes up ↑". Goes to `/scan`.
3. Members only scan sales, so they skip the sheet and go straight to `/scan/sale`. If a member opens `/scan` directly, they are sent to `/scan/sale`.
4. The camera header shows "Scanning: Sale" or "Scanning: Stock in". The mode can't be changed on the camera screen. To change it, close the camera and tap Scan again.
5. The review title and Save button come from the scan's own type, so a scan reopened from "Needs review" also shows the right words.
6. A new product found on a stock-in scan starts with a category guessed from its name (`web/src/app/scan/guess-category.ts`), for example Boysen goes to Paint. If nothing matches it stays Others. Staff can change it on the review line.

**Why**
- Choosing the mode on purpose, every time, is what prevents a delivery being saved as a sale. That is why the sheet has no remembered default and the camera has no toggle.
- The sheet uses the native `<dialog>` element, like the confirm dialog: focus stays inside it, Escape closes it, and focus returns to the Scan button. Every target is at least 48px tall.
- The Scan button no longer opens the phone's camera directly. The in-app camera screen comes first so the mode is visible before the photo is taken.

## Mascot, theme and brand

The rules come from `docs/SUKAT_MASCOT_SPEC.md`. Where this file and the spec disagree, the spec wins.

**What**
- **Theme:** dark is the default. Light and System are kept once picked (`web/src/lib/theme.ts`). `useTheme()` (`web/src/lib/use-theme.ts`) gives the saved choice, the theme on screen and a setter. The colors in `globals.css` are the spec's dark and light tokens. Autofilled inputs keep the surface color instead of the browser's blue.
- **Static mascot:** `<Mascot emote="..." size={n} glow />` (`web/src/components/mascot.tsx`) shows `/mascot/sukat-{emote}-{light|dark}.svg` for the theme on screen, with alt text. `glow` adds a soft orange glow behind it.
- **Animated mascot:** `<SukatMascot motion="..." size={n} />` (`web/src/components/sukat-mascot.tsx` and `.css`) is the rig from `docs/sukat-mascot-motion.html`, with the same layers and keyframes. Each mascot gets its own gradient ids. When the phone asks for reduced motion, it holds its first pose and doesn't move.
- **Logo:** `<SukatLogo height={n} />` (`web/src/components/sukat-logo.tsx`) shows `sukat-logo-pullout-{light|dark}.svg` for the theme on screen, at 345:98, with alt "Sukat". The letters are already shapes, so no font is needed. It sits at the top of Home at 32px. It is never shown under 28px; small places (favicon, app icon, bottom nav) use `sukat-icon.svg` or `sukat-mark-small.svg`.
- **Icons:** the app icons (`icon-192.png`, `icon-512.png`, `apple-touch-icon.png`) are `sukat-icon.svg` on a #1C1917 rounded tile. `icon-maskable-512.png` is the same art inside the safe zone on a full square, for Android. The favicon is `sukat-mark-small.svg`, with `favicon.ico` made from it for older browsers.

**Where each one is used**

| Place | Mascot |
|---|---|
| Sign in, Create an account, Set up your store | `wave` (animated) |
| Ask Sukat welcome | `wave` (animated) |
| Ask Sukat answering | `thinking` (animated) |
| Scan reading the photo | `measure` (animated); `error` if it still can't be read |
| Scan saved | `happy` (animated) |
| Review: lines that need a double check | `confused` (animated) |
| Review: all lines read | `scan-done` |
| Photo can't be read / no items on the receipt | `scan-blurry` / `scan-empty` |
| Toasts ("Saved", "Password changed") | `success` |
| Confirm delete and other risky actions | `warning` |
| No internet | `offline` |
| Empty lists | `empty` |
| Search with no results | `searching` |
| Signed out because the session expired | `sleeping` |
| No permission (members on manager pages) | `locked` |
| Request failed | `error` |

**Why**
- Motion goes on moments that pass: a welcome, an answer on its way, a scan, a save, something to check. Screens that stay put (empty lists, offline, no permission) use the still emotes, so there's never more than one moving thing on screen.
- The logo switches with CSS (both files in the page, one hidden), the way the Next.js image docs show for themed images. Choosing the file in JavaScript would show the dark logo for a moment to light-mode users while the page loads.
- The maskable icon is separate because Android crops it into its own shape. A rounded tile with clear corners would get a black ring.
