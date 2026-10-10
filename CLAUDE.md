# SAPS KZN demo

Citizen -> desk -> HQ demo for SAPS KwaZulu-Natal. The idea: the citizen app presents as **calling 10111** but the call is answered by our backend control-room desk, because the real 10111 line has long delays and many unanswered calls. **Demo only.** Calls and reports go to a demo desk. No real dispatch. A human stays in the loop. Seed records are synthetic and marked so.

Repo: `https://github.com/nordienmn/nordien-saps-kzn` (private). Repo root is this folder. Grok's original build is tagged `grok-demo-v1`. The rebuild is on branch `review/claude-2026-10-10` until merged to `main`.

@~/.claude/shared/shared-context.md

## What it is

Flask + gunicorn, Jinja templates, vanilla JS (no build step), one design system (`static/css/tokens.css`, `components.css`, `app.css`; source and mockups in `design/`). ONE worker on purpose: live data is held in memory and written through to Firestore when `STORE=firestore`.

| Page | Who | Notes |
|---|---|---|
| `/citizen` (`/`) | public, phone | POPIA notice, English and isiZulu, Emergency ("Calling 10111"), crime report (photos, video, location, map pin), GBV help, anonymous tip with a one-time code, unsafe place, profile |
| `/desk` | officers | Officer ID + desk password. Doors: Calls, Crime, GBV, Tip-off line, Infrastructure. Drag a file onto a box (Flying Squad, stations, units, partners) to send it for action |
| `/commissioner` | HQ | Board password. Needs-HQ-action list, anonymous tip oversight, deployments, crime and people (gender, age), referrals and directions, performance, access log, daily brief |
| `/weather` | public, phone | Hidden GBV door. Hold or double-tap the weather icon, confirm, triage, quick exit |
| `/unit` and `/unit/<id>?k=<token>` | stations, units, partners | Each action point's own page by private link. Shows only its tasks. Acknowledge, on scene, cleared / complete |
| `/whatsapp` | Twilio webhook | Mounted only when Twilio settings exist |

Old addresses (`/headoffice`, `/brief`, `/municipality`, `/flying`, `/partner` ...) redirect.

## The flows (do not break these)

- **Call:** citizen starts a call (rings the desk), the desk gets an incoming-call card with sound, Answer, then text chat and live captions (browser speech recognition, shown as it is said). Demo limit: a live call lasts **1 minute**; an unanswered one is closed after 90 seconds. With Twilio Video keys the call is real voice and video, and the desk records it automatically (five-second chunks) onto the file.
- **Anonymous tip:** citizen -> desk **tip-off line** checks it (verify with a note) and acts on it -> a **verified referral for HQ action** -> HQ acknowledges, directs a SAPS unit, or closes. HQ also sees every tip as it arrives (oversight), including unverified ones. The citizen can follow a tip's progress with the one-time code (`GET /api/c/tip/<code>`).
- **Referral vs direction:** a referral goes OUT of SAPS (Thuthuzela Care Centres belong to the NPA, shelters, clinics, municipalities). A direction goes DOWN to a SAPS unit from HQ with an instruction and a due time. See `docs/COMMISSIONER-MODEL.md`.
- **Action points:** stations take deployments; units and partners take referrals. Each has a private link (`saps.service.unit_token`, HMAC of `SECRET_KEY`, so `SECRET_KEY` must be stable in production or links break on restart).

## Rules the code enforces (do not weaken)

- Tips are stored apart from cases with no name, number, device id or IP. Only a hash of the one-time code is kept.
- GBV and weather-SOS records are restricted: names hidden in lists, every open is audit-logged.
- The board feed carries no personal data. Cells under 5 for restricted records show as "<5". GBV, SOS and tips are never map points.
- Gender and age are optional, self-described, used only in grouped statistics, never next to a name.
- Cluster comes from coordinates (nearest centre) or is `unlocated`. It is never defaulted.
- Pages render citizen text with `textContent` only. Never `innerHTML` with data.
- Captions are browser speech or typed text and are never labelled AI. "This call is recorded" is shown only when the server reports a recording is really running.
- An optional profile photo can never block a call or report.
- No secrets in code. All config is environment variables (see `.env.example`).

## Run locally

```
.venv\Scripts\python app.py
```
Needs a `.env` (copy `.env.example`; passwords for desk and board, `SECRET_KEY`, `ADMIN_TOKEN`). Tests: `.venv\Scripts\python -m pytest -q`.

## Deploy (check this section is still true before using it)

Cloud Run, region `africa-south1`, GCP project `nordien-saps-kzn` (billing already on; do NOT create another project). One instance (min 1, max 1). All settings are passed as environment variables, never baked into the image. Safe release: deploy a new revision with `--no-traffic --tag next`, check it at the tag URL, then move traffic. The previous revision stays for rollback. Production settings are kept in `.env.production` (git-ignored) on the owner's machine.

- Live service: `saps-kzn`. Firestore: `STORE=firestore`, same project and region, collections prefixed `saps_`. Evidence videos and call recordings: Cloud Storage bucket named in `MEDIA_BUCKET` (memory only if unset).

## Twilio (optional, secondary)

Real video calls need a Twilio **API key** (SID + secret). WhatsApp needs the auth token and a sender. The Municipal app's WhatsApp webhook already uses the account's sandbox number, so SAPS must not take that webhook over without the owner's decision.
