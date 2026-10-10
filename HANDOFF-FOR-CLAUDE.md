# SAPS KZN demo — handoff for Claude

From: Grok
Date: 2026-10-10
For: Claude review on a local copy. Do not deploy. Do not change the live demo.

No real passwords, API keys, tokens, or service-account files exist in this project. The only credential is the demo desk password, and it is the literal string 0000, hardcoded in the page.

## 1. Repo
- GitHub: https://github.com/nordienmn/nordien-saps-kzn
- Branch: main
- Latest commit on main at time of writing: 2d95dd9 "Pin drop on report a crime"
- Visibility: the user owns nordienmn. If the repo is private, in GitHub open the repo, Settings, Collaborators, and add Claude's GitHub user. There is no other access step.
- Live: https://saps-kzn-420161470509.africa-south1.run.app
- Current live revision at last deploy: saps-kzn-00012-mwm. Pin drop was committed after that deploy, so the live site may not yet have pin drop on Report a crime until the next deploy.

## 2. How to run on a laptop
- Language: Python 3.12
- Framework: none. Standard library only. http.server.ThreadingHTTPServer
- Dependency file: none. No requirements.txt. No npm. No package.json.
- Start command, from the project folder: python server.py
- Port: 8080. Read from the environment variable PORT. If PORT is not set, it uses 8080.
- Environment variables: only PORT. No database URL, no API key, no secret.
- Then open http://localhost:8080/citizen

## 3. How data is stored
- In memory. Two Python lists in server.py: REPORTS and TIPS.
- No SQLite. No Firestore. No file database.
- Data is lost when the server restarts.
- Data is not shared across instances. Cloud Run is set to max 1 instance so the demo does not split. If more than one instance ran, each would have its own lists and the desk would not see the citizen.

## 4. Logins
- Citizen: no login. POPIA gate on every open. Accepting it only hides the gate for that page load. It is not stored.
- Desk: one window. Dropdown chooses the door: Call operators, Crime reporting, GBV, Anonymous. Officer ID is a free-text field, default OP-12. Password is checked in the browser against the literal 0000. It is set in desk.html, in the input value and in the enter() check. It is not checked on the server.
- Commissioner: no login. The page is open.
- No other test logins.

## 5. Pages and API routes

Citizen
- / and /citizen — citizen.html
- Static: /static/badge.png, /static/face.jpg

Desk
- /desk — desk.html

Commissioner / senior leadership
- /commissioner — commissioner.html
- /headoffice — redirects to /commissioner

Weather / GBV cover
- /weather — weather.html

Other pages that exist but are not product doors
- /brief — daily counts
- /municipality — unsafe-area list
- /flying, /cluster, /station, /fcs, /hold, /ems, /durban, /umlazi, /chatsworth, /pmb, /richards — portal.html filtered by path

API
- GET /api/reports — returns REPORTS + TIPS as JSON
- POST /api/reports — creates a file. kind "tip" makes a TIP number. kind "area" makes an MUN number. anything else makes a CAS number.
- POST /api/route/{id} — updates an existing file: officer, verified, desk, call, transcript, log

## 6. Deploy
- Dockerfile: FROM python:3.12-slim, WORKDIR /app, COPY ., ENV PORT=8080, CMD ["python", "server.py"]
- No Cloud Build config file. No deploy script.
- Service name: saps-kzn
- Project: nordien-saps-kzn
- Region: africa-south1
- Memory: 512Mi
- CPU: 1
- Min instances: 1
- Max instances: 1
- Allow unauthenticated: yes
- Command used:
  cd ~/nordien-saps-kzn && git pull && gcloud run deploy saps-kzn --source . --project nordien-saps-kzn --region africa-south1 --allow-unauthenticated --min-instances 1 --max-instances 1 --memory 512Mi --cpu 1 --quiet

## 7. Calls — what is real and what is simulated
- Not WebRTC. There is no signalling server, no peer connection, no TURN.
- The citizen camera and microphone are real where the browser allows it. navigator.mediaDevices.getUserMedia is called. Video call asks for audio and video. Voice call asks for audio. The citizen sees their own preview on video.
- The control-room person is a static image, /static/face.jpg. The desk does not see or hear the citizen. There is no live media path to the desk.
- "10111" is a label on the call screen. The app does not dial the real 10111. There is no tel: link.
- Recording is not saved. No audio file is written.
- The transcript is placeholder text. citizen.html has a list called DEMO_LINES. A timer posts those lines into the file every 2.5 seconds through POST /api/route/{id}. It is not speech-to-text.
- Mute, Camera, Speaker and End change the local screen only. They do not control a real call.

## 8. Case files
- Numbering is a counter in server.py, SEQ, starting at 4206.
- Named or ordinary report: CAS {n}/10/2026, stored in REPORTS, kind "case".
- Anonymous: TIP {n}/10/2026, stored in TIPS, kind "tip". No name stored.
- Unsafe infrastructure: MUN {n}/10/2026, stored in REPORTS, kind "area".
- GBV: CAS number, label "GBV", stored in REPORTS.
- Weather SOS: CAS number, label "GBV SOS", stored in REPORTS.
- A call creates a CAS file with label "Voice call" or "Video call" and call set to "incoming", then updated to "live".
- All of these live only in the process memory.

## 9. Handoffs
- Desk to senior leadership: the Anonymous door has an Escalate button. It POSTs to /api/route/{id} with desk "commissioner" and a log line. That sets status to "referred".
- Referred and escalated are the same mechanism. There is no separate state machine.
- A referred tip flashes red on the commissioner page when kind is "tip" and desk is "commissioner" or status is "referred".
- GBV referral is a button on the GBV door. It appends a log line. It does not create a second file or notify a hospital.

## 10. Commissioner board
- The numbers are counted in the browser from GET /api/reports.
- The filters are filled from the same list: station, area/cluster, crime type/label, place/address, date.
- The cluster map is a drawn SVG of KZN. Dot positions are hardcoded in commissioner.html. Dot size comes from the count of files in that cluster. It is not a map service and not GPS.
- Seed data is in server.py: an armed robbery in Durban Central, a house break-in in Pinetown, a GBV in Umlazi, a park report in Chatsworth, and one anonymous tip in Inanda. Live citizen submissions are added on top. All of it is lost on restart.

## 11. Weather door
- /weather is a cover page. It does not show SAPS branding as the main face.
- The SOS button POSTs to /api/reports with label "GBV SOS".
- That file then appears in the desk GBV door, because the desk filters GBV on label "GBV" or "GBV SOS".
- Location is taken if the browser allows it. Otherwise a placeholder place is sent.

## 12. Privacy
- Anonymous tips store no name and no mobile.
- A named profile is stored only in the browser, in localStorage, key saps-profile. It is not on the server until a report is sent. If a report is sent with a profile, name, mobile and address are in the in-memory file.
- The commissioner page shows whatever is on the file. It does not hide identity on GBV or on named cases.
- Photos: the profile photo stays in the browser. The server stores a path to the sample face image for named files. Citizen evidence uploads are not stored on the server.
- Recordings: none stored.
- Retention: until the process restarts.
- Audit trail: a log list on the file. It records escalate, refer, and transcript lines. It does not record who viewed a file.

## 13. Original brief
The product was specified in chat, not in a single brief file. The intended shape:
- Citizen face.
- One desk. One window. Dropdown logins for Call operators, Crime reporting, GBV, Anonymous. Password 0000.
- Head office and commissioner are the same person. High-level view with station, area, crime, date, place, and a cluster map.
- GBV weather is a hidden door.
- Call shows 10111 and goes to this desk, not the national centre.
- Pin drop and current location on crime reporting.
- English and isiZulu.
- Human in the loop. No auto-dispatch.

## 14. Tested and not tested
Tested on the live site before later changes: POPIA agree, isiZulu label change, back buttons, page load of the doors.
Not tested end to end after the last desk and commissioner rebuilds: call to desk, transcript on the file, anonymous escalate to red flash, GBV referral, pin drop on crime, weather SOS into the GBV door, commissioner filters against live data.

Known shortcuts
- Transcript is fake.
- Call is not a call between two people.
- Password is client-side only.
- No persistence.
- Commissioner map is a drawing.
- Pin drop on crime uses a random KZN coordinate if the browser location is refused. Current location uses the real browser geolocation if allowed.
- Desk crime door excludes tips, areas, GBV, and calls. Unsafe infrastructure is not a door on the current desk dropdown.
- headoffice.html is a redirect, not its own board.

## 15. Reset and current test data
- Reset: restart the server. On Cloud Run, deploy again. There is no reset button and no admin route.
- Seed data shipped in server.py: CAS 4206 armed robbery Durban Central, CAS 4204 house break-in Pinetown, CAS 4203 GBV Umlazi, MUN 4202 park Chatsworth, TIP 4205 suspicious vehicle Inanda.
- Anything else on the live demo was created by use and will vanish on the next restart or deploy.
