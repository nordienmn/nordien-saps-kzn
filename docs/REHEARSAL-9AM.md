# Presenting the SAPS KZN demo: rehearsal sheet

All passwords are `0000`. Use **Google Chrome** (or Edge) on the laptop. Captions and the camera work best there.

## Before you start (5 minutes)

1. Open these two windows on the laptop (put them side by side):
   - Desk: `https://saps-kzn-420161470509.africa-south1.run.app/desk`
   - HQ board: `https://saps-kzn-420161470509.africa-south1.run.app/commissioner`
2. On your phone open `https://saps-kzn-420161470509.africa-south1.run.app/citizen` and tap "I understand and agree".
3. Sign in to the HQ board: password `0000`. Press **Reset demo** (top right) so the data is back to the starting set.
4. Sign in to the desk: choose a **Section**, type any name, press **Take photo** (allow the camera when Chrome asks), then password `0000`.
   - If the camera is blocked, a button "Sign in without a photo (flagged)" appears. It works, and HQ sees it flagged.
5. Use a second browser or a private window if you want the desk and the HQ board signed in at the same time. Two windows in the same browser share one sign-in, so signing in to one signs the other out.

## The story, in order (about 8 minutes)

**1. The call (Call centre section, 2 minutes)**
- Desk window: sign in as **1. Call centre**.
- Phone: tap the big red **Emergency**. The screen says "Calling 10111" and rings.
- Desk: an incoming-call card appears. Press **Answer**.
- Phone: type a message ("I cannot speak safely"). Desk: type a reply. Both sides see it at once.
- Say: "The citizen thinks they are calling 10111. They are answered in seconds by our control room, not after 30 minutes." The call ends itself at one minute (demo rule).

**2. A crime report with evidence (Desk section, 2 minutes)**
- Sign out of the desk (**Switch section**, take the photo). Sign in as **2. Desk**.
- Phone: **Report a crime**, choose a type, tap **Use my current location**, add a photo, **Send report**. The phone shows a reference number.
- Desk: the file is at the top of the queue. Open it. In **Send for action**, **drag the file onto a box** (the Flying Squad, or a police station), or tap the box. Confirm.
- Open a new tab at `https://saps-kzn-420161470509.africa-south1.run.app/unit` (same browser, so you stay signed in) and click the station you sent it to. That is the station's own page. Press **Acknowledge**, then **On scene**, then **Cleared**.

**3. The anonymous tip (Tip-off line then HQ, 2 minutes)**
- Phone: **Report anonymously**, choose a type, place, **Send tip**. Note the one-time code.
- Desk: sign in as **3. Tip-off line**. Open the tip, press **Verify** (write a short note), then **Refer to HQ**.
- HQ board: it appears at the top in red under **Needs HQ action** as a verified referral. Press **Acknowledge**, then **Direct** to a SAPS unit (for example Provincial Crime Intelligence) with an instruction.
- Say: "HQ also sees every tip as it comes in, even the ones the desk has not verified." Open the **Anonymous tips** tab.

**4. GBV (30 seconds)**
- Phone: open `/weather`. It looks like a weather app. Double-tap the small cloud icon. Answer "Are you safe right now?", add a number, **Send to the desk**.
- Desk: sign in as **4. GBV**. The file is marked restricted. Say that opening it is logged.

**5. HQ board (2 minutes)**
- **Overview**: needs-decision list, map, "Calls answered in 30 seconds" next to the national 10111 figure.
- **Deployments**: which stations are out and how fast they arrive.
- **Crime and people**: types, hours, gender and age in groups only.
- **Sign-in records**: a folder for each section with every officer's sign-in and sign-out and photos.
- **Access log**: who opened which restricted file.

## If something goes wrong

| Problem | What to do |
|---|---|
| Camera blocked on the desk sign-in | Use "Sign in without a photo (flagged)". Or click the padlock in Chrome's address bar, allow the camera, and press Take photo. |
| "Too many attempts" at sign-in | Wait one minute. |
| The map is blank or grey | The venue Wi-Fi is blocking map pictures. The board still works. Carry on. |
| A call ends by itself | It is meant to: demo calls last one minute. |
| Live captions do not appear | Captions need Chrome with the microphone allowed. Typed messages always work. |
| The data looks messy after practising | Board, top right, **Reset demo**. |
| The page will not load | Check the phone or laptop is online, then reload. The data is stored in the cloud and will still be there. |
| You need the old version back | Tell me. It is one command to restore the previous version. |

## What to say if asked

- **Is the call real?** The ring, the answer, the messages and the file are real. In this demo the conversation is typed, because live voice needs the Twilio video setting, which is not switched on yet.
- **Is any data real?** No. Everything is synthetic. The demo is clearly labelled at the top of every page.
- **Is the 10111 figure official?** It comes from a written reply to Parliament (response times as of 30 April 2026). It measures the police response, not how fast calls are answered, and the board says so.
- **Why can't the GBV desk see crime files?** By design. Each section sees only its own work, and the server enforces it.
