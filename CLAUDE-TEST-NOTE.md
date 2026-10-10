# SAPS KZN demo — developer note for Claude

From: Grok
For: Claude
Date: 2026-10-10
Project: nordien-saps-kzn
Repo: https://github.com/nordienmn/nordien-saps-kzn
Live: https://saps-kzn-420161470509.africa-south1.run.app

## Why this note
The user cannot enter the app. The first screen is a POPIA gate. The "I agree" button on the currently live revision does not open the app. That is the first thing to test and fix if still broken after redeploy.

## What is already on GitHub (main, commit 7b529bc)
citizen.html was rewritten. The previous live file had a broken script: `openPanel` was missing its function header, so the page script failed and `accept()` never ran. That is why "I agree" did nothing.

The rewrite includes:
- Fixed `accept()` and `openPanel()`
- SAPS KZN branding: navy `#0a2f6b`, gold `#c5a059`, red emergency `#c8102e`
- English / isiZulu toggle, stored in localStorage as `saps-lang`
- Back button on every form panel
- POPIA gate still first; accept stores `saps-popia=yes` and hides the gate

## Live status at time of this note
The Cloud Run service is still serving the old broken citizen page. The user has not yet pulled and redeployed the fix. Until that deploy finishes, the phone will keep showing the broken "I agree".

Deploy command already given to the user:
```
cd ~/nordien-saps-kzn
git pull
gcloud run deploy saps-kzn --source . --project nordien-saps-kzn --region africa-south1 --allow-unauthenticated --min-instances 1 --max-instances 1 --memory 512Mi --cpu 1 --quiet
```

## Test this, in order
1. Open https://saps-kzn-420161470509.africa-south1.run.app/citizen on a phone and on a desktop.
2. Confirm the first screen is the POPIA gate.
3. Tap "I agree". The gate must close and the app must be usable. If it does not, the live revision is still the old one, or the script is still broken.
4. Confirm navy SAPS header, gold badge, and English / isiZulu switch.
5. Switch to isiZulu. Labels must change. Switch back to English.
6. Open Emergency, Report a crime, GBV help, Anonymous, Unsafe area, and Profile. Each must have a Back button that returns to the home buttons without clearing the whole flow.
7. From citizen, send one named report and one anonymous tip. Open https://saps-kzn-420161470509.africa-south1.run.app/desk and confirm the named report is in the operator queue and the tip is not.
8. Open /weather and confirm the GBV cover still posts into the same backend.
9. Open /headoffice, /commissioner, /municipality, /brief and confirm each loads.

## Doors
- Citizen: /citizen
- Desk: /desk
- Weather cover: /weather
- Head office: /headoffice
- Commissioner: /commissioner
- Municipality: /municipality
- Brief: /brief

## Constraints from the user
- Demo only. No real personal data.
- Human stays in the loop. No auto-dispatch.
- Anonymous is a tip, not a case, and must not sit in the normal operator queue.
- Profile photo must be taken on the camera, not chosen from a file.
- Language matters: English and isiZulu on the citizen door.
- Branding must look like SAPS KZN, not a generic iPhone form.
- The first button on the app must work. If the user cannot get past "I agree", the demo has failed.

## Ask
Please test the live link after the user redeploys. If "I agree" still fails, fix citizen.html on main and tell the user the exact Cloud Shell command to pull and deploy. Do not add a new GCP project. Billing is already on nordien-saps-kzn.
