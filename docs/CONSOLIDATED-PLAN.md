# SAPS KZN demo: consolidated plan

Combines Claude's review (`docs/REVIEW-2026-10-10.md`) with Kimi's build pack. 2026-10-10.

**How to read this**

- Claude's review is an audit of what exists. Every finding there is labelled live, local or code-read.
- Kimi's pack is a build spec. It is mostly proposals, not findings about the current app. I checked its factual claims (table below). I could **not** check its 40-test list, schemas or seed script: the file path in the paste was blank and only the summary reached me.
- This plan keeps what is supported, changes what conflicts with how we build, and defers the rest.

## Kimi claims checked

| Claim | Result |
|---|---|
| Firestore supports `africa-south1` | **Supported.** Listed as a supported location (added April 2024). Same region as the Cloud Run service. |
| Twilio Video is a safe choice | **Supported.** Its planned shutdown was reversed in October 2024. |
| Daily.co plus Deepgram live transcription | **Supported.** Daily offers Deepgram-powered live transcription and 10,000 free participant-minutes a month (from third-party pricing pages; check Daily's own pricing before relying on it). |
| Thuthuzela Care Centres exist in KZN | **Supported.** The NPA's list (30 March 2026) names KZN sites including Eshowe, Estcourt and KwaDukuza. Seed from the NPA list, not from the pack. |
| Single "hold 2 seconds" button aligns with "NG112 silent-call requirements" | **Partly supported.** EENA confirms silent calls and text emergency contact are real needs. NG112 is a European standard and does not specify a hold button. Hold-to-activate can also block people with motor difficulty, so give it an alternative. |
| Quick-exit "wipes the back-stack" | **Overstated** [MEMORY]. A web page can replace its own history entry and jump to a neutral site. It cannot erase earlier entries. Promise less in the copy. |
| Anonymous tip sends no token and no device ID (test A15) | **True today** (code-read): payload is type, place, note. Caveat: Cloud Run's own request logs can still hold the sender's IP address [MEMORY], so do not promise "untraceable". |
| Header should be fixed ("COMMISSIONER · KZN · Desk") | **True.** The header reads COMMISSIONER · KZN with a "Desk" link beside it. |
| An all-zero board reads as broken | **Not a current problem.** The live board starts with 5 seed records. Still good advice once persistence lands. |
| Case reference visible within 5 seconds, call state machine, reference artefact on every submission | **Right, and missing today.** The call shows "Calling 10111" throughout, and the confirmation is off-screen. |
| Two-field minimum submit | **Today there is no validation at all**: an empty crime report can be sent. |

## Where Kimi's plan conflicts with how we build

1. **Firebase "callable functions" and a Node seed script.** Our family is Python and Flask on Cloud Run, and Municipal already pairs that with Firestore. Keep the Python server as the only writer to Firestore. Write the seed in Python. No second runtime.
2. **Firebase Anonymous Auth for citizens.** Not needed. The citizen path stays "no profile, still goes through". Tips must stay free of any identity or auth linkage.
3. **Real partner names in referrals.** Demo only. Seed the structures and names from the NPA list, with clearly fake contact numbers and a "demo, nothing is dispatched" label.
4. **Scope.** The pack describes a multi-phase product. Do it in the order below, not all at once.

## Order of work

**Phase 0: honesty and safety (before anyone senior sees the demo)**
- DEMO banner on every page and on the call screen. "This demo does not reach 10111."
- Stop the false claims (location, recording, Mute, Speaker). Remove or make them real.
- Escape every field. Protect the write routes. Fix the static-file traversal. Add a token-protected reset route.
- Visible confirmations. Visible escalation strip on the board. Weather door: confirm step and quick exit.
- GBV form carries a callback number, location and a safe-contact choice.

**Phase 1: design system and visible surfaces** (Claude with the `ui-ux-designer` agent)
- Shared tokens, type scale, SVG icons, components, for all seven pages.
- Citizen: one Emergency button with an accessible alternative to hold, call states (Connecting, Ringing, Connected with a timer, Ended), a reference screen after every submission, a one-time code for anonymous tips, a triage-first GBV form ("Are you safe right now?"), a two-field minimum for crime reports, full isiZulu, notice as a real dialog, camera and file attachments that actually upload.
- Desk: priority queue with age and status chips, an action on every card, call card with live timer, case file with photo and map, alert on new items.
- Board: real map, honest KPIs (open vs closed), cleaned filters, pinned escalations strip, reduced-motion safe.

**Phase 2: persistence and referrals** (same GCP project `nordien-saps-kzn`, no new project)
- Firestore in `africa-south1`, written only by the Python server. The user must enable the API and create the database if the signed-in gcloud account lacks permission.
- Case numbers per station and year. Tips stored separately with no identity link.
- Referral objects with a status chain (created, sent, acknowledged, completed) and a consent gate: contact details flow to a partner only if the citizen agreed. "Call me now" becomes an urgent desk task. Unsafe-infrastructure reports get their own chain to the municipality.
- Seed 30 to 50 synthetic cases, clearly marked synthetic, including a staged anonymous tip for the red-flash moment.

**Phase 3: real calls (optional, after Phase 1)**
- Daily.co or Twilio Video, with Deepgram transcription through Daily. The user creates the account and supplies the API key; I will not enter it for them. Citizen video leaves our GCP project, so keep it demo-only and say so.

**Rehearsal**
- Use Kimi's checklist idea: golden path under four minutes, a screen-recorded fallback on a second laptop, and a seeded fallback for the red-flash moment. Build the final checklist from the pack once the file is available.

## Kimi's deep-dive review: claims tested

Kimi sent two documents: the build pack above, and a door-by-door "shortcomings and improvements" review. Here is the second one, tested against the code and the saved copy of the live pages. Most of it is proposals, which I can't "test", so I list only what claims something about the app as it is today.

**Confirmed (matches what I found or can reproduce)**

- The call screen shows a LIVE badge from the first second while the text says "Connecting…". No Ringing, Connected or timer states exist.
- No recording notice anywhere on the citizen side. No visible failure path: every submit function awaits the network with no error handling, so with no signal the screen just stays as it is (code-read).
- The Call button never dials 10111. There is no phone-dialer fallback.
- Mute, Speaker and Camera: Mute and Speaker are label-only. Camera-off leaves a black or broken panel.
- No anonymous receipt code. The crime and tip confirmations exist but are off-screen on a phone.
- GBV wording differs between the main app and the weather door ("Hospital?" vs "Hospital or clinic", "Call you now?" vs "Should someone call you now?"), and "Can you identify the person?" appears in both.
- GBV referral is only a log line. No referral object, no partner, no status.
- No quick-exit anywhere. No queue position, no case age or SLA colours, no status buttons.
- Commissioner header: "COMMISSIONER · KZN" with an unexplained "Desk" link beside it. The "Movement" section is simply the case feed, and its label says nothing.
- Commissioner filters ignore the URL (no URL-parameter code).
- `/headoffice` is only a redirect to the commissioner page.
- isiZulu is partial.

**New and worth adopting** (I had not listed these)

- Queue behaviour when several calls land at once (position for the citizen, depth for the desk).
- Case age colours (green, amber, red).
- URL-persisted board filters; one geography hierarchy instead of three overlapping filters.
- Suppress or blur map dots when a cluster has fewer than 5 cases, so a single GBV report can't identify a person.
- A "Restricted record, access logged" badge on GBV and anonymous files at board level (the badge is a UI line; real access control is Phase 2 and later).
- Crime type dropdown aligned to the SAPS categories, in both languages.
- A safety line on photo prompts: "Only take a photo if it is safe."
- A one-line reason next to each rule the citizen has to follow.
- Friend contact in the weather door: **in the code the friend is never contacted.** The name and number are saved on the phone and pasted into the SOS note as text. Kimi asks to define what the friend receives; the honest answer is that today they receive nothing.

**Not supported, or wrong about the current build**

| Kimi claim | What the code and pages show |
|---|---|
| The desk login prints "Password is 0000" | That line is hidden until a wrong password is entered. The real problem is that the field is pre-filled with the password, so there is no password in practice. |
| The crime form shows only "Place", with no location button or pin | It has "Current location" and "Drop pin" buttons, and the pin works (but gives a random coordinate; see my report). |
| Time is a free field | It is a date-time picker. The real fault: the value is thrown away on submit. |
| The crime report gives the citizen nothing after submit | A case number does appear, but off-screen on a phone. |
| Unsafe infrastructure needs a category list and shows "A file photo is not accepted" | It already has a ten-item list (Dark street, Broken light, Open ditch and so on). It has no photo field at all. The "file photo is not accepted" wording is on the profile page. |
| Anonymous photo is enforced | `capture="environment"` is only a hint, and the photo is never sent. |
| Every counter reads 0 | Not on the live site, which starts with 5 seed records. |
| The red flash may break the WCAG limit of three flashes a second | It is a 1 Hz pulse with reduced opacity, which is within the limit. The real problems are its position below the fold and no reduced-motion setting. |
| Case numbers might differ across surfaces | They match: the same CAS number shows on the citizen confirmation, the desk and the board (the format is not station-based, which is a separate gap). |
| Show an "AI-assisted transcript, operator confirms" badge | There is no AI. The transcript is four scripted lines. A badge saying otherwise would be untrue. |
| The weather door is a single page hidden behind a thin weather cover | It is one of ten random covers. One tap on the main button sends the SOS. Kimi's gesture and confirm advice is right, but the problem is bigger than described. |

**Overstated or unverified**

- "NG112 requirements are non-negotiable": NG112 is a European framework. Good guidance, not a South African obligation.
- "POPIA requires informed, specific consent": consent is one lawful basis among several. A notice duty applies regardless [MEMORY]. The section numbers cited (retention and security) look right [MEMORY]. Have someone qualified confirm before the notice copy is finalised.
- The Namola/iER hold-button pattern, UK Bright Sky and "SA GBV app patterns" were not verified.
- "The concept is world-class and prototypes the NG112 future": unsupported. Do not use that line in the room.

**Could not test**

- Two officers on two doors at once. The Officer ID is only text in the browser and the server has no session, so the claim is almost meaningless today.
- Speaker routing, low-end Android performance, throttled 3G first paint.

## What to give Grok

Give Grok this plan and the Claude review, not Kimi's text. Where Kimi found something new, it is credited above.
