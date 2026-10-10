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

## What to give Grok

Give Grok this plan and the Claude review, not Kimi's text. Where Kimi found something new, it is credited above.
