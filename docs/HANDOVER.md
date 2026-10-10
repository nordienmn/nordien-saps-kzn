# SAPS KZN demo: handover

Built 2026-10-10 on branch `review/claude-2026-10-10`. Grok's original is tagged `grok-demo-v1` and is still in git history.

## Addresses (all under `https://saps-kzn-420161470509.africa-south1.run.app`)

| Page | Path | Sign in |
|---|---|---|
| Citizen app | `/citizen` | none (phone) |
| Weather door (hidden GBV help) | `/weather` | none (phone) |
| Control room desk | `/desk` | pick a section (Call centre, Desk, Tip-off line, GBV), type any name or number, take the sign-in photo with the camera, password `0000` |
| HQ board (Commissioner) | `/commissioner` | password `0000` |
| Action points | `/unit` (list, after desk or board sign in); each point has a private link `/unit/<id>?k=<token>` | the link itself |

All passwords are `0000` (the owner's decision for a demo with no real data). Other keys live in `.env.production` on the owner's computer (git-ignored) and are set as Cloud Run environment variables; they are not in the code or the image. Allow the browser to use the camera on the desk page.

## Before a showing

1. Open the board, press **Reset demo** (top right) to put the data back to the starting set.
2. Open the desk in one window and the citizen app on a phone (or a phone-size window).
3. Hand-rehearsed paths: (a) citizen calls, desk answers, types back, call ends itself at one minute; (b) citizen sends an anonymous tip, desk verifies it and refers it to HQ, HQ acknowledges and directs Crime Intelligence; (c) citizen reports a crime, the desk drags the file onto a station box, the station's own page acknowledges and clears it, and the board's deployment figures move.

## What is real and what is not

- Real: every screen, every hand-off, the data model, the audit log, the access rules, the HQ statistics, per-action-point pages, drag and drop, evidence upload, the one-minute demo call limit.
- Real once the owner adds Twilio **Video** keys: voice and video calls, with automatic recording onto the file. Until then a call is the real ring and answer plus typed messages and captions. The screen says so.
- Live captions use the browser's own speech recognition (works in Chrome and Edge, English only; isiZulu speech is not supported by browsers). They can be wrong. They are never labelled AI.
- WhatsApp bot and friend alerts are built and switched off until Twilio settings are added (see CLAUDE.md). The Municipal app already owns the Twilio sandbox webhook, so SAPS must not take it over without a decision.
- The 10111 comparison on the board uses national figures reported to Parliament (written reply, as of 30 April 2026). They measure the police response time, not how fast a call is answered, and the board says so. The reply PDF itself could not be opened by the tool used, so the figures come from the search summary and should be checked before they are quoted to the client.
- isiZulu is a first draft and needs a native-speaker check. The same applies to the legal wording of the privacy notice.
- Station positions and cluster groupings are approximate and illustrative (KwaZulu-Natal has about 184 stations in more clusters than the 10 shown).

## Rollback

Each release is a Cloud Run revision. To go back to Grok's version, send traffic to revision `saps-kzn-00014-qlh`:

```
gcloud run services update-traffic saps-kzn --to-revisions saps-kzn-00014-qlh=100 --region africa-south1 --project nordien-saps-kzn
```

## Next steps (not blocking the demo)

- Twilio Video: create an API key in the Twilio console and give the SID and secret to the deploy settings (`TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`).
- Decide the WhatsApp number (separate sender, or a menu entry in the Municipal bot).
- Self-host the fonts and use a licensed map tile source before anything beyond a demo.
- Real sign-in for officers and units (per-person accounts), a records-retention rule, and a security review.
