# SAPS KZN demo — review brief for Claude and Kimi

From: Nordien Consulting / Grok
Date: 2026-10-10
Product: SAPS KZN citizen and desk demo
Repo: https://github.com/nordienmn/nordien-saps-kzn
Live revision: saps-kzn-00009-n46
Cloud Run: https://saps-kzn-420161470509.africa-south1.run.app
Project: nordien-saps-kzn
Region: africa-south1

This is a live demo for senior SAPS KZN management. Demo only. No real personal data. No real 10111. A human stays in the loop. Nothing is auto-dispatched.

## What the product is
A citizen phone app and a police desk for KwaZulu-Natal.

The citizen can:
- Accept a POPIA notice before use. The notice is the landing page every open.
- Press Emergency. Call and Video call sit on the same red button. The call takes the whole screen. Mute, Camera, Speaker, End. The citizen sees the control-room person. The call is recorded and a transcript writes into the case file.
- The call says 10111 but goes to the SAPS KZN desk, not the national 10111 centre.
- Report a crime in writing, with type, time, place, description, photo or video.
- Report anonymously. No name is stored. This is a tip, not a case.
- Open GBV help: social worker, hospital, identify the person, call now, transport.
- Report unsafe infrastructure: dark street, broken light, ditch, veld, path, vagrants, unsafe building, park, taxi rank, school grounds.
- Create a profile. The photo must be taken on the camera, not chosen from a file. Name, mobile and address then fill in on reports and calls.
- Switch English / isiZulu.

The desk is one page with four sections next to each other. Each has its own sign-in. Password for every section is 0000.
- Call operators — voice and video calls
- Crime reporting — written reports from the app
- GBV — GBV only, with referral buttons
- Anonymous — tips only, can escalate to senior leadership

Head office and Commissioner are the same person. Both links open the senior leadership view. They see everything: cases, GBV, unsafe infrastructure, and anonymous tips. A tip referred up flashes red.

Weather is a hidden GBV door. It looks like a weather page. The SOS goes to the same desk.

## Links
- Citizen: https://saps-kzn-420161470509.africa-south1.run.app/citizen
- Desk: https://saps-kzn-420161470509.africa-south1.run.app/desk
- Senior leadership / Commissioner: https://saps-kzn-420161470509.africa-south1.run.app/commissioner
- Head office: https://saps-kzn-420161470509.africa-south1.run.app/headoffice (same door as Commissioner)
- Weather cover: https://saps-kzn-420161470509.africa-south1.run.app/weather
- Brief: https://saps-kzn-420161470509.africa-south1.run.app/brief
- Municipality: https://saps-kzn-420161470509.africa-south1.run.app/municipality
- Flying Squad: https://saps-kzn-420161470509.africa-south1.run.app/flying

## Technical specs
- Static HTML doors served by a Python ThreadingHTTPServer.
- In-memory REPORTS and TIPS lists. Polling every 2 seconds. No database. Restart clears the files.
- Numbering: CAS for named cases, TIP for anonymous, MUN for unsafe infrastructure.
- POST /api/reports creates a file. POST /api/route/{id} updates desk, officer, call, transcript, log.
- Role filtering is in the page, not in a separate backend.
- POPIA gate is client-side and shows on every open.
- Call screen uses getUserMedia where the browser allows it. Transcript lines are written into the file for the demo.
- Deploy: Cloud Run, africa-south1, unauthenticated, min 1, max 1, 512Mi, Dockerfile.
- Languages on the citizen door: English and isiZulu.
- Branding: SAPS badge, navy #0a2f6b, gold, red emergency.

## What to do
1. Review and test. Follow every item from the citizen action to its final point. Do not stop at the citizen screen.
2. Check design and functionality.
3. Compare to global police-app standards. Use Dubai Police Eye, Abu Dhabi Aman, Tokyo Digi Police, and Beijing 110 as the reference set. Do not use app-store reviews.
4. Give a functionality report.
5. Give recommendations to improve, based on those global standards.

## Test each point to its end
Open the citizen link and the desk link at the same time. On the desk, enter each section with password 0000.

1. POPIA. Open citizen. The first screen must be the notice. Tap I agree. The app must open. Close and reopen. The notice must show again.
2. Language. Switch to isiZulu. Labels must change. Switch back.
3. Voice call. Tap Call. The whole screen must become the call. Other buttons must disappear. Mute, Camera, Speaker, End must be there. A transcript must start writing. On the desk, enter Call operators. The call must appear there with the transcript. End the call. The file must remain.
4. Video call. Tap Video call. Same full screen, with the citizen camera if the browser allows it. It must land in Call operators.
5. Crime report. Send a written report with type, place and description. Enter Crime reporting on the desk. The file must be there with a CAS number.
6. Profile. Create a profile with a camera photo, name, mobile, address. Send another report. The name must appear on the desk file.
7. Anonymous. Send an anonymous tip. It must appear only in the Anonymous section, not in Crime reporting or Call operators. Escalate it. Open Commissioner. The tip must appear in the anonymous section, and flash red if referred up.
8. GBV. Send GBV help. It must appear in the GBV section. Use a referral button. The log must record it. It must also be visible to Commissioner.
9. Unsafe infrastructure. Send one, for example Park or Vagrants. Confirm where it lands, and that Commissioner can see it.
10. Senior leadership. Open /commissioner and /headoffice. They must be the same view. It must show cases, GBV, unsafe infrastructure, and anonymous.
11. Weather. Open /weather. Confirm it is a cover, and that an SOS from it reaches the same desk.
12. Branding. Confirm the SAPS badge is on the citizen header and the desk.

## Report format
For each of the 12 points: Pass or Fail, what you saw, where it stopped if it failed.

Then:
- Design notes. What looks amateur. What is clear.
- Functionality notes. What works end to end. What breaks.
- Global comparison against Dubai Police Eye, Abu Dhabi Aman, Tokyo Digi Police, Beijing 110. Anonymous versus named, evidence, language, call handling, senior oversight.
- Recommendations, in priority order, that can be built into this demo without adding a new GCP project.

Do not create a new Google Cloud project. Billing is already on nordien-saps-kzn. If a fix is needed, change the repo and give the exact Cloud Shell command:

cd ~/nordien-saps-kzn && git pull && gcloud run deploy saps-kzn --source . --project nordien-saps-kzn --region africa-south1 --allow-unauthenticated --min-instances 1 --max-instances 1 --memory 512Mi --cpu 1 --quiet
