# Sukat mascot + UI spec

## Files
- public/mascot/sukat-{emote}-{light|dark}.svg — 16 static emotes
- public/mascot/sukat-icon.svg — app icon art (put on a dark #1C1917 rounded tile)
- public/mascot/sukat-mark-small.svg — simple mark for 16–32px (favicon)
- public/mascot/sukat-logo-pullout-{light|dark}.svg — main logo (wordmark uses Outfit 800)
- docs/sukat-mascot-motion.html — animated rig (SVG + CSS keyframes), 7 motions

## Emote → app state
| Emote | Use |
|---|---|
| normal | Welcome, sign in, AI chat start |
| thinking | AI answering, "Reading receipt..." |
| happy | Saved! |
| success | Task done toast |
| confused | "Please check this line" |
| error | Request failed |
| warning | Confirm delete / risky action |
| offline | No internet |
| empty | Empty list |
| searching | Search with no results |
| sleeping | Session expired |
| locked | No permission |
| scanning | Camera reading paper |
| scan-blurry | Photo can't be read |
| scan-empty | No items found on receipt |
| scan-done | Scan finished |

## Motion → app state
idle (default), walk (onboarding/page change), wave (sign in, chat welcome),
thinking (AI/loading), happy (saved), confused (needs review), measure (scanning, splash).

## Colors
Dark: bg #1C1917, surface #292524, border #44403C, text #FAFAF9, muted #A8A29E, link #FB923C, button #C2410C
Light: bg #F5F5F4, surface #FFFFFF, border #D6D3D1, text #1C1917, muted #57534E, link #C2410C, button #C2410C
Status dark: red #FCA5A5 on #450A0A, amber #FCD34D on #422006, green #86EFAC
Status light: red #B91C1C on #FEE2E2, amber #92400E on #FEF3C7, green #15803D

## Fonts
UI: Inter. Logo wordmark: Outfit 800 (outline it in the final logo file).
