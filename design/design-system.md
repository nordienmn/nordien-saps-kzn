# SAPS KZN design system v1.0

Written 2026-10-10 for the rebuild of the SAPS KZN demo. Demo only: no real 10111, a human stays in the loop.

Files in this folder:

| File | What it is |
|---|---|
| `tokens.css` | Every colour, size, spacing, radius, shadow, duration and z-index, as CSS variables. Two themes. |
| `components.css` | All shared components. Needs `tokens.css`. |
| `icons.svg` | 56 line icons (24px grid, 1.75 stroke), drawn for this system. |
| `badge.png` | An unchanged copy of the real SAPS badge, so the mockups open anywhere. The app keeps using its own copy in `static/img/`. |
| `citizen-home.html`, `citizen-call.html`, `citizen-confirmation.html`, `desk.html`, `commissioner.html`, `weather-cover.html` | The six mockups. Plain HTML, small inline scripts, open by double-clicking. |

Open any mockup in Chrome or Edge. The grey "Mockup controls" panel (bottom right) is presentation scaffolding, not part of the app.

---

## 1. Why the old demo looked amateur, and what this fixes

The review (section 5) found seven pages with seven looks, no icons, no motion, no states, a hand-drawn map, and a desk list with no hierarchy. A competent colour change would not fix that. What fixes it:

| Failure in the old demo | What replaces it |
|---|---|
| Seven hard-coded palettes | One token file, two themes, one palette family |
| Nothing says "this is SAPS" except a gold pill | Navy and badge gold used with discipline, a seal plate for the real badge, a gold hairline under every header |
| No type voice | A deliberate pairing (section 3) |
| Zero icons | One icon family, always paired with a word |
| Confirmation 570px below the fold | A full reference screen with a ticket-style slip, case number, "what happens next" and a saved image |
| No call states | Connecting, Ringing, Connected (timer), Ended, each with its own screen state and announcement |
| Desk list is flat grey text | Priority bar, P1 to P4 chip, age dot, status chip, one primary action per case |
| Hand-drawn SVG polygon map | Real OpenStreetMap tiles with merged metro bubbles and a graceful static fallback |
| Flash below the fold | An escalations strip pinned under the header, slow glow, still visible with reduced motion |

### Design principles (written to be argued with)

1. **Red is a verb, not a colour.** Signal red appears only where a person needs a human now: the Emergency control, an incoming call, an open escalation, the End button, a P1 chip. It is never a decoration, never a header, never a hover. If red is everywhere, the real emergency is invisible. (Julie Zhuo's test: a principle should name a decision another team would not make.)
2. **Calm for the person in danger, loud for the officer.** The citizen and GBV screens use soft surfaces, plain words and no urgency theatre. The desk incoming-call card is deliberately the loudest object on any screen in the product.
3. **Consent never blocks help.** The POPIA notice is a real dialog, but "Call 10111" is a button inside it, and the Emergency control is not gated behind legal text.
4. **Say what is simulated.** Captions are labelled "Simulated in this demo". The word "AI" appears nowhere. Recording is a flag (section 9), never an assumed fact.
5. **Fine is free now, so add back the human detail** (Katie Dill). The reference slip has notched edges, the check mark draws itself once, the Emergency icon gives three slow rings on load and then stops. Small, finite, never looping on the citizen side.

Evidence base, briefly: Jakob's Law (call controls follow phone-call conventions, answer is green, end is red), Fitts's Law (Emergency and primary actions are large and low on mobile), Hick's Law (five tiles, not twelve; four case actions, not nine), progressive disclosure (the GBV form shows only "Are you safe right now?" until it is answered), Peak-End (the reference screen is the last thing a citizen sees, so it is the most crafted), Doherty (skeleton rows on desk load), Maeda's gulf of evaluation (every desk action produces a visible status change, a timeline line and a toast), Microsoft's "when the system is wrong" (the offline banner on the desk, the unreachable-map fallback). EskomSePush is the local precedent for "one glance" civic information; the commissioner board follows that, and the geography hierarchy (province, district, station) is a single control rather than three overlapping filters.

---

## 2. Palette

One family: SAPS navy, SAPS gold, one signal red. Cool slate neutrals. Not Municipal (charcoal and crimson `#c10d42`), not Ancestors or Library (bone, brass, serif).

### Light theme (citizen), `data-theme="light"` (the default)

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--color-bg` | `#f3f5f9` | page | text 15.7:1 |
| `--color-surface` | `#ffffff` | cards, sheets | text 17.1:1 |
| `--color-text` | `#0f1b33` | body | |
| `--color-text-muted` | `#4a5873` | secondary | 7.2:1 on white |
| `--color-text-subtle` | `#5f6d86` | captions, placeholders | 5.2:1 |
| `--color-border-strong` | `#74839b` | control edges | 3.8:1 |
| `--color-primary` | `#14377a` navy | main button | 11.3:1 with white |
| `--color-accent` | `#c9a03a` gold | hairlines, decoration only | not for text |
| `--color-accent-text` | `#7a5a12` | gold when it must be text | 6.4:1 |
| `--color-emergency` | `#c9291a` | Emergency only | 5.5:1 with white |
| `--color-emergency-text` | `#a3141b` | red as text on light | 7.9:1 |
| `--color-focus` | `#1f4fa3` | focus ring | 7.8:1 |

### Ops theme (desk, commissioner), `data-theme="ops"`

Navy-black, not charcoal. Set per page with the attribute. `prefers-color-scheme` is deliberately not used: a control room must not change look because of a phone setting.

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--color-bg` / `--color-surface` / `--color-surface-2` | `#08142b` / `#0e1f3e` / `#142a52` | layers | text 14.7:1 on surface |
| `--color-text-muted` | `#aebcd4` | secondary | 8.5:1 |
| `--color-text-subtle` | `#93a3c0` | meta | 6.4:1 |
| `--color-border-strong` | `#6580b0` | control edges | 4.1:1 |
| `--color-primary` | `#e3b94f` gold | main button (the one confident accent) | 9.9:1 with navy text |
| `--color-emergency-text` | `#ff7a70` | red as text on dark | 6.4:1 |
| `--color-answer` | `#2fbf71` | ANSWER | 7.8:1 with dark text |
| `--color-focus` | `#f5cf6b` | focus ring | 10.9:1 |

### Status and priority (both themes, always paired with a word or icon)

| Meaning | Tokens | Where |
|---|---|---|
| New / waiting | `--status-warning-*` | chip "New" |
| Accepted / info | `--status-info-*` | chip "Accepted" |
| Referred | `--status-handoff-*` (teal) | chip "Referred" |
| Escalated / error | `--status-danger-*` | chip "Escalated", form errors |
| Closed / success | `--status-success-*` | chip "Closed" |
| Neutral | `--status-neutral-*` | caption chips |
| Priority P1 to P4 | `--prio-1-*` red solid, `--prio-2-*` amber solid, `--prio-3-*` blue, `--prio-4-*` grey | queue, case file |
| Case age | `--age-ok`, `--age-warn`, `--age-late` (under 10 min, under 20, beyond) | age dot |
| Restricted record | `--restricted-*` | lock badge |

Gold is brand decoration and the ops primary action. It is never a status colour; warning is an orange-amber, always with a word. Every foreground/background pair in `tokens.css` was run through a script (checked in this session): 0 failures against 4.5:1 for text and 3:1 for control edges, focus rings and status solids, in both themes.

---

## 3. Typography

**Pairing:** Barlow Semi Condensed (display, numerals, case numbers) + Public Sans (all reading text).

Why this pair, and not a serif or a stock system stack:

- Our other apps own serif and charcoal. SAPS needs its own voice.
- Barlow comes from highway and number-plate signage. That is the visual world of police vehicles, road signs and station boards, so it reads institutional without needing decoration. Its semi-condensed width also keeps long isiZulu headings ("Isimo esiphuthumayo", "Ihhovisi Lokulawula le-SAPS KZN") and 2x text size from wrapping badly, and its numerals are tabular, which makes case numbers, timers and KPIs align.
- Public Sans was designed for government interfaces (US Web Design System). It stays legible at small sizes on cheap Android screens and has the weight range we need.
- Cost: two families, seven font files, roughly 60 kB. Load once per page with `display=swap`. Fallbacks (Arial Narrow, system-ui) look acceptable if the fonts fail. The weather cover loads no web fonts at all, on purpose.

Scale (major third, ratio 1.25, base 16px, all `rem` so it follows the user's text size):

| Token | Size | Use |
|---|---|---|
| `--fs-xs` | 12.8px | uppercase labels and chips only |
| `--fs-sm` | 14px | dense ops meta only |
| `--fs-base` | 16px | all reading text (citizen minimum) |
| `--fs-md` | 20px | card titles, queue age |
| `--fs-lg` | 25px | section titles, reference number |
| `--fs-xl` | 31px | page titles, Emergency |
| `--fs-2xl` / `3xl` / `4xl` | 39 / 49 / 61px | timers, KPIs |

The commissioner board sets `data-surface="board"` on `<html>`, which raises the root size to 18px (and 20px at 1600px+). Everything is `rem`, so the whole board scales from one switch and stays readable across a boardroom.

Spacing is a 4px base on an 8px rhythm (`--space-1` to `--space-16`). Radius: `--radius-xs` 4, `sm` 8, `md` 12, `lg` 16, `xl` 24, `pill`. Shadows `--shadow-1/2/3`, `--shadow-emergency`. Motion: `--dur-fast` 140ms, `--dur-base` 220ms, `--dur-slow` 300ms (ceiling), `--ease-out`, `--ease-spring`, `--pulse-period` 2.4s. Z-index: base 0, raised 10, sticky 100, header 200, banner 300, dropdown 400, overlay 500, dialog 600, toast 700, skip 800.

---

## 4. Components and the rules for using them

| Component | Classes | Rule |
|---|---|---|
| DEMO banner | `.chrome > .demo-banner` with `.demo-banner__tag` | On every page, sticky, one line where it fits. Never dismissible. Text is honest and specific ("Does not reach 10111"). |
| Header + brand | `.app-header`, `.app-header--ops`, `.brand`, `.brand__seal`, `.brand__name`, `.brand__sub` | The real badge goes on a white seal plate, unchanged. Gold hairline under every header. |
| Buttons | `.btn` + `--primary` `--secondary` `--ghost` `--emergency` `--answer`, `--lg`, `--block`, `--icon` | One primary per screen. Minimum 44px high. Emergency and answer variants are for their jobs only. |
| Segmented control | `.segmented`, `.segmented__btn`, `.segmented__count` | Language, doors, period, status. State is `aria-pressed` or `aria-selected`. |
| Emergency hero | `.emergency`, `__main`, `__icon`, `__title`, `__sub`, `__alt`, `__alt-btn` | The only large red object on citizen home. One tap calls; there is no hold gesture, because holds exclude people with motor difficulty. The guard against accidents is the Cancel on the Connecting screen. |
| Tile | `.tile-grid`, `.tile`, `__icon`, `__title`, `__desc`, `.tile--wide`, `.tile--care` | Five at most on home. Every tile has a one-line reason. |
| Card | `.card`, `--flat`, `--sunken`, `--tight`, `__head`, `__title` | |
| Status chip | `.chip` + `--new` `--accepted` `--referred` `--escalated` `--closed` `--neutral`, `--dot` | Always a word. |
| Priority chip | `.prio--1` to `.prio--4` | "P1 Critical". The queue row also carries a coloured edge bar. |
| Restricted badge | `.restricted` | Exact text: "Restricted record - access logged" on every GBV and anonymous item at desk and board level. |
| Form field | `.field`, `__label`, `__hint`, `__error`, `.input`, `.select`, `.textarea`, `.field--error` | Every control has `<label for>` and hints/errors tied by `aria-describedby`. |
| Choice cards | `.choice-group`, `.choice`, `__title`, `__hint` | Radios and checkboxes as large tap targets. |
| Banner | `.banner` + `--info` `--success` `--warning` `--danger` `--restricted` `--neutral` | |
| Dialog and sheet | `.dialog`, `.dialog--sheet`, `__accent`, `__body`, `__foot` | Native `<dialog>` with `showModal()` for focus trap and inert background. Bottom sheet on phones. |
| Toast | `.toast-region` (an `aria-live` region), `.toast` | Confirms every desk action and every copy or save. |
| Timeline | `.timeline`, `--compact`, `__item--done` `--current`, `__dot`, `__time`, `__title`, `__text` | Citizen "what happens next" and desk event log. |
| Queue row | `.queue`, `.queue-row`, `--p1` to `--p3`, `__main`, `__title`, `__meta`, `__side`, `.age`, `--warn`, `--late` | A whole row is one button, 76px tall. |
| KPI tile | `.kpi`, `__label`, `__value`, `__sub`, `__spark`, `--alert`, `--restricted` | |
| Filter bar | `.filter-bar`, `__group`, `__label`, `__spacer` | One geography control (province, district, station). State persists in the URL hash. |
| States | `.state`, `__icon`, `__title`, `__text`, `--error`, `--success`, `.skeleton`, `.skeleton--row`, `.spinner` | Every list has loading, empty and error. |
| Call screen and controls | `.call` (with `data-state`), `__top`, `__avatar`, `__facts`, `__body`, `__bottom`, `.call-controls`, `.call-btn`, `--end`, `--answer`, `.silent-prompt`, `.stepper`, `.fact` | Icon plus label always. Mute, camera and speaker are disabled until Connected. |
| Transcript | `.transcript`, `__list`, `__line`, `--you`, `__who`, `__text` | The container is `role="log"`. Header always carries "Simulated" or "Live captions". |
| Incoming call card | `.incoming-call`, `--active`, `__icon`, `__tag`, `__name`, `__meta`, `__actions`, `__timer` | Loudest object in the product. Interrupts every door. |
| Case file | `.casefile`, `.action-bar`, `.avatar`, `.person`, `.kv` | Accept, Refer, Escalate, Close, sticky under the header. |
| Escalations strip | `.escalations`, `.escalation`, `.is-new`, `.is-ack`, `__new` | Pinned under the header. Pulse is a 2.4s box-shadow glow (0.42 Hz). |
| Reference slip | `.reference`, `__label`, `__code`, `__divider`, `.codebox`, `__char`, `.check-badge` | The citizen's last screen. |
| Map | `.map`, `__canvas`, `__fallback`, `__legend`, `.pin`, `--suppressed`, `--alert`, `--case` | See section 8. |
| Quick exit | `.quick-exit` | Visible on every GBV surface. |
| Utilities | `.stack`, `.cluster`, `.sr-only`, `.skip-link`, `.num`, `.ref`, `.label-caps`, `.icon`, `.icon--sm/lg/xl` | |
| Mockup only | `.mock-rail` | Do not ship. |

Icons: `<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-phone"/></svg>`. Names: phone, end-call, video, video-off, mic, mic-off, camera, camera-off, speaker, speaker-off, shield, shield-check, map-pin, crosshair, alert, lamp, building, users, user, heart, eye-off, lock, clock, check, check-circle, chevron-right/left/down, close, exit, globe, info, plus, search, filter, bell, sliders, record, chat, silent-text, send, escalate, referral, file, inbox, image, download, copy, plus weather-only: sun, cloud, cloud-sun, cloud-rain, wind, droplet, sunrise, thermo.

---

## 5. Motion

- Under 300ms for every UI transition; springs have a small overshoot and settle fast; sheets slide from the bottom.
- Looping motion is limited to: the incoming-call rings and the escalation glow (period 2.4s), the connecting dashed ring, the spinner and the skeleton shimmer. Nothing flashes. Nothing exceeds 1Hz.
- `prefers-color-scheme` is not used. `prefers-reduced-motion: reduce` collapses all durations in `tokens.css` and forces one-shot animations. The pulses become a static state that is still visible by colour, border and the "NEW" tag. The signal is never lost, only the movement.

---

## 6. Accessibility rules (WCAG 2.2 AA)

1. Contrast 4.5:1 for text, 3:1 for control edges, focus rings and status colours, both themes (script-checked).
2. Touch targets 44px minimum, including segmented buttons, call controls (64px), rows and icon buttons. Sizes are `rem`, so they grow with text size.
3. Visible focus everywhere: 3px outline with 2px offset, navy on light, gold on dark. Programmatic heading focus (dialog titles) shows no ring but is announced.
4. Real structure: `header`, `nav`, `main`, `section` with headings, one `h1` per page, skip link. Labels use `for`. Tabs use `role="tablist"` with arrow keys.
5. Announcements: reference confirmation is `role="status"`; call state is `role="status"`; captions are `role="log"`; toasts are in an `aria-live` region; the timer is `aria-live="off"` so it does not read every second.
6. Dialogs are native `<dialog>` with a titled `aria-labelledby`.
7. No emoji. Icons are `aria-hidden` and always sit next to text or inside a control that has a label.
8. `lang` follows the language switch on `<html>`; isiZulu buttons carry `lang="zu"`.
9. 2x text size: the citizen layouts reflow to one column and nothing is clipped (checked on home in isiZulu at 200%; the Emergency title breaks inside long words rather than overflowing). Tile grid, call controls and code boxes wrap.
10. Colour is never the only signal: status chips have words, priority has "P1", age has a number and an accessible "overdue" label.
11. The weather cover's trigger is unlabeled on purpose (`aria-label="Current conditions"`). A hidden control is by nature undiscoverable; the one-time "How to ask for help" explainer lives in the setup screen and hold, double-tap and keyboard (Enter twice, or hold Enter) all work.

---

## 7. Page-to-component map (for the implementer)

| Template (route) | Theme | Build from |
|---|---|---|
| Citizen home (`/citizen`) | `light` | `.chrome/.demo-banner`, `.app-header`, `.lang-bar`, `.segmented`, `.emergency`, `.tile-grid/.tile`, `.banner`, `.dialog--sheet` (POPIA) |
| Citizen forms (crime, GBV, anonymous, unsafe place, profile) | `light` | `.field`, `.input/.select/.textarea`, `.choice-group/.choice`, `.btn--primary`, `.banner--warning` for safety lines, `.quick-exit` on GBV |
| Citizen call | `ops` on this page only | `.call`, `.call-controls`, `.silent-prompt`, `.stepper`, `.transcript`, `.dialog--sheet` |
| Citizen confirmation | `light` | `.check-badge`, `.reference`, `.codebox`, `.timeline`, `.toast` |
| Desk (`/desk`) | `ops` | `.chrome`, `.app-header--ops`, `.segmented[role=tablist]`, `.queue/.queue-row`, `.incoming-call`, `.casefile`, `.action-bar`, `.card`, `.kv`, `.timeline--compact`, `.transcript`, `.map`, `.dialog`, `.state`, `.skeleton` |
| Commissioner (`/commissioner`) | `ops` + `data-surface="board"` | `.escalations`, `.kpi`, `.filter-bar`, `.map`, `.pin`, `.card`, `.chip`, `.restricted` |
| Weather cover (`/weather`) | `light`, own look | Its own CSS for the cover face; `.dialog--sheet`, `.choice`, `.btn`, `.quick-exit` for the help sheet |
| Partner (`/partner`) | `light` | `.card`, `.timeline`, `.chip--referred`, `.restricted`, `.kv`; show contact details only when the citizen consented |
| Infrastructure and municipality share | `light` | `.card`, `.chip`, `.kv`, `.banner--neutral` |

Rules for the build:

- Link `tokens.css` then `components.css` on every page; set `data-theme` and (board only) `data-surface` on `<html>`. Page-level CSS is for layout only.
- Load Barlow Semi Condensed and Public Sans with one `<link>` (see top of `components.css`). The weather cover loads none.
- Inline `icons.svg` once in the base template (`{% include %}`). External `<use href="icons.svg#...">` does not work from `file://` and is slower; inline works everywhere.
- Never `innerHTML` with data. The mockups build every case, report and caption with `textContent`; keep that (the only `innerHTML` in the mockups is the static fallback SVG and the translation of fixed strings that contain bold labels).
- Leaflet: `unpkg.com/leaflet@1.9.4`. Keep the "OpenStreetMap contributors" attribution visible. Dark ops maps are the standard OSM tiles inverted by `--map-tile-filter`; no second tile provider.
- The Content-Security-Policy must allow `fonts.googleapis.com`, `fonts.gstatic.com`, `unpkg.com`, `tile.openstreetmap.org`.
- `.mock-rail` and the `?state=`, `?lang=`, `?zoom=` test parameters are scaffolding. Do not ship them.

---

## 8. Map, privacy and the board

- Real tiles when reachable; if the CDN or tiles fail, the static KZN outline with the same bubbles replaces it, so the board is never blank in a boardroom with bad Wi-Fi. (Test with "Show map fallback" in the mockup controls.)
- The eThekwini stations merge into one bubble while zoomed out (the old board stacked Pinetown, Chatsworth and Durban on top of each other). Selecting the bubble, or choosing a district in the Area control, zooms in and splits it.
- Areas with fewer than 5 cases render as a dashed "<5" ring. GBV and anonymous items are totals only and are never placed on the map. Restricted-record totals below 5 show as "<5". Say this on the board; the note is part of the layout.
- Filters live in the URL hash (`#p=7d&a=eThekwini%20metro&t=Armed%20robbery&s=open`) so a view can be shared and survives refresh.
- The board carries no names, numbers or photos. The desk shows names for ordinary cases and hides them for GBV until "Open restricted record" is pressed, which writes a timeline line ("Access logged"). The access log itself is a build item (section 10).

---

## 9. Honest-claims rules the design enforces

| Surface | Claim | Rule |
|---|---|---|
| Call screen | "This call is recorded" | Driven by one flag. The brief asks for this line, but the repository's `CLAUDE.md` says recording is off. The mockup shows both strings (rail: "Recording on/off"). Ship "This call is not recorded. Captions are saved to your case." until recording really exists. |
| Captions | "Simulated in this demo" or "Live captions" | Never "AI". The desk uses "Live captions, simulated". |
| Location | "Sharing your approximate location" | Show it only when a location was actually sent; otherwise "Location is off. You can type the place instead." |
| Anonymous | "No identity was sent" | True by design. The "How anonymous is this?" panel also says hosting logs may hold technical records, and that anonymous is not untraceable. |
| Friend text | "We also sent a message to your friend" | Today the friend receives nothing (consolidated plan). The mockup shows the sentence only because a friend was entered in the setup. Do not ship the sentence until the text is actually sent. |
| Referral | "Nothing is dispatched" | The refer dialog says so in the demo. |
| What happens next | No promised response times | The timeline describes steps, not minutes. |

---

## 10. What is a recommendation and what needs a build decision

Ready to build from now: tokens, components, icons, all layouts, copy.

Needs a decision or more work before it is real:

1. **Recording line** (above).
2. **Friend notification**: define what the friend receives. Suggested text: "[Name] asked you to check on them. Please call them." No police name, no reason. Optional approximate area, off by default.
3. **Weather cover data**: the mockup uses plausible fixed values and the device clock. A cover that shows stale temperatures will be noticed. Pull a real forecast or label nothing as live.
4. **Cover and the browser**: the tab title "Weather" and a neutral icon help, but the URL and permission prompts can still expose the site name. Quick exit returns to the cover and cannot erase browser history.
5. **Restricted access log**: the desk mock writes a timeline line; a real, queryable audit log is a Phase 2 item.
6. **Offline queue**: the copy for "No signal, saved on this phone" is in the deck but needs an actual queue.
7. **OpenStreetMap tiles** are fine for a demo. A live service needs a commercial or self-hosted tile source (the standard tile servers forbid heavy use).
8. **Google Fonts** sends the visitor's IP to Google. Fine for the demo; self-host the fonts before production (a POPIA point).
9. **isiZulu**: every isiZulu string below needs a native-speaker check. Several (the POPIA clauses, "restricted") need a legal-plain-language pass as well.
10. **Hold-to-activate**: not used anywhere on the citizen Emergency control. On the weather cover, hold or double-tap is the right trade-off because it must be hidden; both are offered, plus keyboard.

Not done in these mockups: the crime, anonymous, unsafe-place and profile form screens (specified here and in the copy deck, built from `.field`, `.choice` and `.btn`); the partner page; a real photo or camera capture; a real call or real captions; the desk's sound beyond a two-tone beep when "Ring incoming call" is pressed (browsers block autoplay audio until a user gesture).

---

## 11. Copy deck (plain language, English and isiZulu)

Every isiZulu string below is **needs native-speaker check**. Reading level target: 12-year-old. No jargon. No blame. "GBV" appears only where a helpline or the officer needs it; the citizen tile says "Help after abuse or violence".

### 11.1 Home and notice

| Key | English | isiZulu |
|---|---|---|
| demo banner | Demonstration only. This does not reach 10111. In an emergency, call 10111. | I-demo kuphela. Ayifinyeleli ku-10111. Esimweni esiphuthumayo, shayela u-10111. |
| skip | Skip to main content | Eqa uye kokuqukethwe okuyinhloko |
| sub | South African Police Service, KwaZulu-Natal | Amaphoyisa aseNingizimu Afrika, KwaZulu-Natali |
| language | Language | Ulimi |
| h1 | How can we help? | Singakusiza kanjani? |
| lede | Choose what you need. You do not need an account. | Khetha okudingayo. Awudingi i-akhawunti. |
| emergency title | Emergency | Isimo esiphuthumayo |
| emergency sub | Call the SAPS KZN desk now | Shayela ihhovisi le-SAPS KZN manje |
| video call | Video call | Ucingo lwevidiyo |
| silent text | Can't talk? Text us | Awukwazi ukukhuluma? Sibhalele |
| location chip | Your approximate location (Umlazi) is shared when you call or report. | Indawo oyiyo ngokufanele (eMlazi) yabelwana nathi uma ushayela noma ubika. |
| section label | Or report something else | Noma bika okunye |
| tile crime | Report a crime | Bika ubugebengu |
| tile crime desc | Something has happened. Tell us, with photos if it is safe. | Kwenzekile okuthile. Sitshele, nezithombe uma kuphephile. |
| tile GBV | Help after abuse or violence | Usizo ngemva kokuhlukunyezwa |
| tile GBV desc | Calm, private help. You are believed. | Usizo oluthulile nolufihlekile. Siyakukholwa. |
| tile anonymous | Report anonymously | Bika ungaziwa |
| tile anonymous desc | A tip with no name or number sent. | Ithiphu engathunyelwa igama noma inombolo. |
| tile unsafe | Unsafe place | Indawo engaphephile |
| tile unsafe desc | Dark streets, broken lights, open ditches. | Imigwaqo emnyama, amalambu aphukile, imisele evulekile. |
| tile profile | My profile (optional) | Iphrofayela yami (akuphoqelekile) |
| tile profile desc | Add your name and photo once so reports are faster. | Faka igama nesithombe kanye, ukuze imibiko ishesha. |
| helpline title | If it is not safe to use this app | Uma kungaphephile ukusebenzisa le app |
| helpline body | GBV Command Centre: 0800 428 428 (free, 24 hours). Or dial *120*7867# to send a Please Call Me. | Isikhungo Sokuyalela se-GBV: 0800 428 428 (mahhala, amahora angu-24). Noma ushayele *120*7867# ukuthumela i-Please Call Me. |
| privacy link | Privacy notice | Isaziso sobumfihlo |
| notice title | Before you start | Ngaphambi kokuqala |
| notice intro | This notice is given under the Protection of Personal Information Act (POPIA). | Lesi saziso sinikezwa ngaphansi koMthetho Wokuvikelwa Kolwazi Lomuntu Siqu (i-POPIA). |
| notice collect | What we collect: only what you type, upload or choose to share, such as a photo or your approximate location. | Esikuqoqayo: kuphela lokho okubhalayo, okufakayo noma okukhethayo ukukwabelana, njengesithombe noma indawo oyiyo ngokufanele. |
| notice why | Why: so SAPS can respond to your report. It may be used as evidence. | Isizathu: ukuze i-SAPS iphendule umbiko wakho. Ungasetshenziswa njengobufakazi. |
| notice who | Who sees it: authorised SAPS officers only. Abuse reports and anonymous tips are restricted, and every access is logged. | Obonayo: amaphoyisa agunyaziwe kuphela. Imibiko yokuhlukunyezwa namathiphu angaziwa avikelwe, futhi ukufinyelela ngakunye kuyarekhodwa. |
| notice choice | Your choice: you can report anonymously. We do not need an account. | Ukhetho lwakho: ungabika ungaziwa. Asidingi i-akhawunti. |
| notice demo | This is a demonstration. Nothing you enter here is sent to a real police officer. | Le yi-demo. Akukho okufakayo lapha okuthunyelwa kwiphoyisa langempela. |
| notice agree | I understand and agree | Ngiyaqonda futhi ngiyavuma |
| notice full | Read the full notice | Funda isaziso esigcwele |
| notice call | In danger right now? Call 10111 | Usengcupheni manje? Shayela u-10111 |

### 11.2 Call

| Key | English | isiZulu |
|---|---|---|
| who | SAPS KZN Control Room | Ihhovisi Lokulawula le-SAPS KZN |
| state connecting | Connecting... | Iyaxhuma... |
| state ringing | Ringing the desk... | Iyalila ehhovisi... |
| state connected | Connected | Uxhumile |
| state ended | Call ended | Ucingo seluphelile |
| recorded (only if true) | This call is recorded | Lolu cingo luyarekhodwa |
| not recorded | This call is not recorded. Captions are saved to your case. | Lolu cingo alurekhodwa. Amagama abhalwayo agcinwa kumbiko wakho. |
| location | Sharing your approximate location: Umlazi | Wabelana ngendawo oyiyo ngokufanele: eMlazi |
| reference | Reference | Inombolo yereferensi |
| captions title | Live captions | Amagama abhalwayo ngqo |
| captions chip | Simulated in this demo | Okulingiselwe kule-demo |
| can't talk | Can't talk? Tap here | Awukwazi ukukhuluma? Thinta lapha |
| mute / unmute | Mute / Unmute | Thulisa / Vula umsindo |
| camera | Camera | Ikhamera |
| speaker | Speaker | Isipikha |
| cancel / end | Cancel / End | Khansela / Misa |
| sheet title | Can't talk? Send a message | Awukwazi ukukhuluma? Thumela umyalezo |
| sheet hint | The desk sees your message straight away. Your phone stays silent. | Ihhovisi libona umyalezo wakho ngokushesha. Ifoni yakho ihlala ithulile. |
| quick 1 | I cannot speak safely | Angikwazi ukukhuluma ngokuphepha |
| quick 2 | Someone is in the house | Kukhona umuntu endlini |
| quick 3 | I need an ambulance | Ngidinga i-ambulensi |
| quick 4 | Send help to my location | Thumela usizo endaweni engikuyo |
| own message | Or type your own message | Noma bhala owakho umyalezo |
| send message | Send message | Thumela umyalezo |
| back to call | Back to call | Buyela ocingweni |
| message sent | Message sent to the desk | Umyalezo uthunyelwe ehhovisi |
| ended title | Call ended | Ucingo seluphelile |
| duration | Duration | Isikhathi |
| saved | Saved to your case: Call details and captions | Kugcinwe kumbiko wakho: Imininingwane yocingo namagama abhalwayo |
| still in danger | If you are still in danger, call 10111 now. | Uma usesengozini, shayela u-10111 manje. |
| view reference | View my reference | Buka inombolo yami yereferensi |
| home | Back to home | Buyela ekhaya |

### 11.3 Reference screens

| Key | English | isiZulu |
|---|---|---|
| title | We have your report | Sinawo umbiko wakho |
| lede | Keep this reference number. You can use it to ask about your report. | Gcina le nombolo yereferensi. Ungayisebenzisa ukubuza ngombiko wakho. |
| ref label | Your reference number | Inombolo yakho yereferensi |
| type / place / sent | Type / Place / Sent | Uhlobo / Indawo / Kuthunyelwe |
| copy / copied | Copy / Copied to your clipboard | Kopisha / Kukopishiwe |
| save | Save this screen | Londoloza lesi sikrini |
| saved | Saved as an image | Kulondolozwe njengesithombe |
| next | What happens next | Kwenzekani ngokulandelayo |
| step 1 | Received. Your report is at the SAPS KZN desk. | Kutholiwe. Umbiko wakho usehhovisi le-SAPS KZN. |
| step 2 | An officer reads it. If you gave a phone number, an officer may call you. Keep your phone close. | Iphoyisa liyawufunda. Uma unikeze inombolo yocingo, iphoyisa lingakushayela. Gcina ifoni yakho eduze. |
| step 3 | It may be passed on. A station or a support service may take over. Your reference number stays the same. | Ungadluliselwa kwenye indawo. Isiteshi noma insizakalo yosizo ingathatha. Inombolo yakho yereferensi ihlala injalo. |
| danger | In danger right now? Call 10111. | Usengcupheni manje? Shayela u-10111. |
| anon title | Your tip has been sent | Ithiphu yakho ithunyelwe |
| anon lede | This code is the only way to refer back to your tip. | Le khodi iyona kuphela indlela yokubhekisela ethiphu yakho. |
| no identity | No identity was sent. No name, phone number or profile came with this tip. | Akukho ncazelo ngawe ethunyelwe. Akukho gama, inombolo yocingo noma iphrofayela ehambisane nale thiphu. |
| code label | Your one-time code | Ikhodi yakho esetshenziswa kanye |
| code hint | Shown once. We cannot show it again. You will need it if you want to add to this tip later. | Iboniswa kanye kuphela. Ayikwazi ukuboniswa futhi. Uzoyidinga uma ufuna ukwengeza kule thiphu kamuva. |
| copy code | Copy code | Kopisha ikhodi |
| screenshot safety | Screenshots are saved in your photos. Only save this if it is safe. | Izithombe-skrini zigcinwa kumaphothi akho. Lokhu kulondoloze kuphela uma kuphephile. |
| how anonymous | How anonymous is this? | Ukungaziwa kusho ukuthini? |
| how anonymous body | No name, phone number, profile or device ID is attached to a tip. Technical records kept by the hosting service, such as an IP address, are not linked to your tip in this design. Anonymous is not the same as untraceable. | Akukho gama, inombolo yocingo, iphrofayela noma i-ID yedivayisi enamathiselwe kuthiphu. Amarekhodi ezobuchwepheshe agcinwa yinkampani ehlinzeka ngenkundla, njenge-IP address, awaxhunywanga kuthiphu yakho kule dizayini. Ukungaziwa akufani nokungalandeleki. |
| anon step 2 | An officer reviews it. They see what you wrote and where. They cannot see who you are. | Iphoyisa liyayibuyekeza. Libona lokho obhale kona nokuthi kuphi. Alikwazi ukubona ukuthi ungubani. |
| anon step 3 | Adding more later. Use your code if you want to add to this tip. | Ukwengeza kamuva. Sebenzisa ikhodi yakho uma ufuna ukwengeza kuthiphu. |

### 11.4 Forms (specified here, not mocked up)

| Key | English | isiZulu |
|---|---|---|
| crime title | Report a crime | Bika ubugebengu |
| two-field note | We only need the type and the place. Everything else is optional. | Sidinga kuphela uhlobo nendawo. Konke okunye akuphoqelekile. |
| type label | What happened? | Kwenzekeni? |
| type: armed robbery | Armed robbery | Ukuphangwa ngezikhali |
| type: house break-in | House break-in | Ukugqekezwa kwendlu |
| type: hijacking | Vehicle hijacking | Ukuthathwa ngenkani kwemoto |
| type: theft | Theft | Ukwebiwa |
| type: shooting | Shots fired or shooting | Ukudutshulwa |
| type: assault | Assault | Ukushaywa |
| type: suspicious | Suspicious activity | Isenzo esikhomba ukusola |
| type: other | Something else | Okunye |
| place label | Where did it happen? | Kwenzeke kuphi? |
| use location | Use my current location | Sebenzisa indawo yami yamanje |
| choose on map | Choose on the map | Khetha emephini |
| place hint | Street, suburb or landmark | Umgwaqo, indawo noma uphawu lwendawo |
| location off | Location is off. You can type the place instead. | Indawo ivaliwe. Ungabhala indawo kunalokho. |
| when label | When? | Kwenzeke nini? |
| when options | Just now / Earlier today / Another time | Manje nje / Ekuqaleni kwanamuhla / Ngenye inkathi |
| details label | Tell us more (a few words are enough) | Sitshele okwengeziwe (amagama ambalwa anele) |
| photo label | Add a photo or video | Faka isithombe noma ividiyo |
| photo safety | Only take a photo if it is safe. | Thatha isithombe kuphela uma kuphephile. |
| send report | Send report | Thumela umbiko |
| sending | Sending... | Iyathunyelwa... |
| error type | Please choose what happened. | Sicela ukhethe ukuthi kwenzekeni. |
| error place | Please tell us where. | Sicela usitshele ukuthi kuphi. |
| offline (needs build) | No signal. Your report is saved on this phone and will send when you are back online. | Awukho isignali. Umbiko wakho ugcinwe kule foni futhi uzothunyelwa uma ubuyela online. |
| try again | Try again | Zama futhi |
| anon title | Report anonymously | Bika ungaziwa |
| anon note | We do not ask for your name or number. | Asikubuzi igama noma inombolo yakho. |
| send tip | Send tip | Thumela ithiphu |
| unsafe title | Report an unsafe place | Bika indawo engaphephile |
| unsafe note | This is not a crime report. We can pass it to the municipality. | Lena akuyona imibiko yobugebengu. Singayidlulisela kumasipala. |
| unsafe types | Dark street / Broken light / Open ditch / Overgrown path / Unsafe building / Taxi rank / School grounds | Umgwaqo omnyama / Ilambu eliphukile / Umsele ovulekile / Indlela ephuphumile / Isakhiwo esingaphephile / Isitebhisi / Izwe lesikole |
| send to municipality | Send to the municipality | Thumela kumasipala |
| profile title | My profile | Iphrofayela yami |
| profile photo | Take a photo of yourself | Thatha isithombe sakho |
| name / mobile / address | Name / Mobile number / Address (optional) | Igama / Inombolo yocingo / Ikheli (akuphoqelekile) |
| profile note | Saved on this phone. Used to fill in your reports and calls. | Kugcinwa kule foni. Kusetshenziselwa ukugcwalisa imibiko yakho nezingcingo. |
| save profile | Save profile | Londoloza iphrofayela |
| back / cancel / close | Back / Cancel / Close | Emuva / Khansela / Vala |

### 11.5 GBV and weather cover (calm, believing, non-prosecutorial)

Order matters: "Are you safe right now?" is always first. Everything after it appears only once it is answered. No question is required except the first.

| Key | English | isiZulu |
|---|---|---|
| confirm title | Ask for help? | Ucela usizo? |
| confirm body | A police desk will see your approximate area and can call you back, if you choose. Nothing is sent until you tap Send on the next screen. | Ihhovisi lamaphoyisa lizobona indawo yakho ngokufanele futhi lingakushayela, uma ukhetha lokho. Akukho okuthunyelwayo kuze kube uthinta Thumela esikrinini esilandelayo. |
| confirm demo | This is a demonstration. No real police desk will receive this. | Le yi-demo. Akukho hhovisi lamaphoyisa langempela eliyitholayo. |
| yes / no | Yes, I need help / No, go back | Yebo, ngidinga usizo / Cha, buyela emuva |
| safe title | Are you safe right now? | Uphephile yini manje? |
| safe lede | We believe you. Share only what you want to. | Siyakukholwa. Yabelana kuphela nalokho ofuna ukukwabelana. |
| safe options | Yes, I can talk / No, I am not safe. Send help quietly / I am not sure | Yebo, ngiyakwazi ukukhuluma / Cha, angiphephile. Thumela usizo ngokuthula / Angiqinisekile |
| danger | If you are in danger right now, call 10111. | Uma usengozini manje, shayela u-10111. |
| contact legend | How can we reach you? | Singakuthola kanjani? |
| contact options | You may call me / SMS only / Do not contact me yet | Ningangishayela / Ama-SMS kuphela / Ningangixhumani nami okwamanje |
| needs legend | What would help? (choose any) | Yini engakusiza? (khetha noma yiziphi) |
| needs options | Someone to talk to / Medical care / A safe place or transport | Umuntu okhuluma naye / Ukunakekelwa ngokwezempilo / Indawo ephephile noma ezokuthutha |
| who legend | Do you know who did this? (You do not have to say now.) | Uyamazi yini owenze lokhu? (Akudingeki ukusho manje.) |
| who options | Yes / No / Not now | Yebo / Cha / Hhayi manje |
| send | Send to the desk | Thumela ehhovisi |
| sent title | We have your request | Sinakho ukucela kwakho |
| sent body | A desk officer has it. If you chose to be called, they will call you. | Iphoyisa lasehhovisi linakho. Uma ukhethe ukushayelwa, lizokushayela. |
| friend sent (only if built) | We also sent a message to your friend. | Sithumele nomyalezo kumngani wakho. |
| helpline | GBV Command Centre: 0800 428 428, free, 24 hours. | Isikhungo Sokuyalela se-GBV: 0800 428 428, mahhala, amahora angu-24. |
| done | Done | Kuphelile |
| quick exit | Exit | Phuma |
| quick exit label (screen reader) | Quick exit: return to the weather screen | Phuma masinyane: buyela esikrinini sezulu |
| friend setup title | A friend | Umngani |
| friend setup body | Pick one person you trust. If you ever ask for help from this screen, we can send them a short text so they know to check on you. It never says why. | Khetha umuntu oyethembayo. Uma ucela usizo kulesi sikrini, singathumela umyalezo omfushane ukuze azi ukuthi akubheke. Awusho isizathu. |
| friend name / mobile | Friend's first name / Friend's mobile number | Igama lomngani / Inombolo yocingo yomngani |
| friend location | Include my approximate area in the text (off unless you turn it on) | Faka indawo engikuyo ngokufanele emyalezweni (ivaliwe ngaphandle uma uyivula) |
| how to ask | On the main screen, hold the weather icon for about a second, or tap it twice. A question always comes first, so nothing is sent by accident. | Esikrinini esikhulu, bamba isithonjana sezulu cishe isekhondi, noma usithinte kabili. Umbuzo uhlale uza kuqala, ngakho akukho okuthunyelwa ngephutha. |

### 11.6 Desk and board (English only, for officers)

Desk and board copy is English. Labels used: Calls, Crime, GBV, Anonymous, Queue, All, New, Mine, ANSWER, Pass to next operator, Accept, Refer, Escalate, Close, Open restricted record, "Restricted record - access logged", "Live captions, simulated", Alerts on/off, Leadership board, Control room desk. Board: Escalations, Acknowledge, Received today / in 7 days / in 30 days, Open, Closed, Median time to accept, Restricted records, "Totals only", Period, Area, Crime type, Status, Clear filters, "Where cases are", "Latest movement", "No personal data", and the suppression note.

---

## 12. Verification record

Checked in this session (headless Edge screenshots, not a real phone):

- Citizen home at 375px, English and isiZulu, notice open and closed, and at 200% text size in isiZulu.
- Call screen at 375px, Ringing and Connected, and the isiZulu silent-text sheet.
- Confirmation at 375px, standard and anonymous.
- Desk at 1280px (Crime, GBV, answered call) and 1024px (Anonymous, stacked layout).
- Commissioner at 1440px, with the real OpenStreetMap map, district drill-down and the 7-day period.
- Weather cover at 390px (day and night looks, help triage sheet).
- Token contrast script: 0 failures. Duplicate-id and missing-icon scan across all six pages: none. All form controls have a linked label.

Not checked: a real phone, a real screen reader, real keyboard-only passes on every page, throttled 3G, low-end Android performance, Safari. These need a device pass before the demo is shown.
