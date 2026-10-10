# SAPS KZN demo

Citizen -> desk -> senior leadership demo for SAPS KwaZulu-Natal. **Demo only.** No real 10111, no real personal data, a human stays in the loop. Every page says DEMO. Seed records are marked synthetic.

Repo: `https://github.com/nordienmn/nordien-saps-kzn` (private). Repo root is this folder. Original build by Grok is tagged `grok-demo-v1`. The rebuild lives on `review/claude-2026-10-10` until the owner merges it.

@~/.claude/shared/shared-context.md

## What it is

Flask + gunicorn, Jinja templates, vanilla JS (no build step), one design system (`static/css`). One process on purpose: live data is held in memory and written through to Firestore when `STORE=firestore`.

| Page | Who | Notes |
|---|---|---|
| `/citizen` (`/`) | public | POPIA notice, English and isiZulu, Emergency, crime report, GBV help, anonymous tip, unsafe infrastructure, profile |
| `/desk` | officers | Officer ID + desk password. Doors: Calls, Crime, GBV, Anonymous, Infrastructure |
| `/commissioner` | senior leadership | Board password. No names, numbers or photos ever reach this page |
| `/weather` | public (hidden GBV door) | Looks like another app. Help is a two-step, with quick exit |
| `/partner` | referral partners (demo) | What a receiving partner sees; contact details only if the citizen agreed |
| `/whatsapp` | Twilio webhook | Only mounted when Twilio settings exist |

Old addresses (`/headoffice`, `/brief`, `/municipality`, `/flying`, ...) redirect.

## Rules the code enforces (do not weaken)

- Tips are stored apart from cases with no name, number, device id or IP. Only a hash of the one-time code is kept.
- GBV and weather-SOS records are restricted: names hidden in lists, every open is audit-logged.
- The board feed carries no personal data. Small counts (under 5) for restricted records show as a band.
- Cluster comes from coordinates (nearest centre) or is `unlocated`. It is never defaulted.
- Pages render citizen text with `textContent` only. Never `innerHTML` with data.
- The transcript is live captions (browser speech) or typed text. It is never labelled AI. Recording is off.
- No secrets in code. All config is environment variables (see `.env.example`).

## Run locally

```
.venv\Scripts\python app.py
```
Needs a `.env` (copy `.env.example`). Tests: `.venv\Scripts\python -m pytest -q`.

## Deploy (check this section is still true before using it)

Cloud Run, region `africa-south1`, GCP project `nordien-saps-kzn` (billing already on; do NOT create another project). One instance (min 1, max 1). Settings are passed as environment variables, never baked into the image.

- Rehearsal service: `saps-kzn-next`. Live demo service (Grok's build): `saps-kzn`. Switch only when the owner says.
- Firestore: `STORE=firestore`, same project and region, collections prefixed `saps_`.

## Twilio (optional, secondary)

Real video calls need a Twilio **API key** (SID + secret). WhatsApp needs the Twilio auth token and a sender. The Municipal app's WhatsApp webhook already uses the account's sandbox number, so SAPS must not take that webhook over without the owner's decision.
