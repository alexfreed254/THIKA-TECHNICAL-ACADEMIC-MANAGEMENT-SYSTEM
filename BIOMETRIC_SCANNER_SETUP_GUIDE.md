# TTTI Biometric Fingerprint Scanner — Configuration & Connection Guide

**System:** Thika Technical Training Institute Academic Management System  
**Device:** Suprema BioEntry W2 (or BioEntry W) Fingerprint Scanner  
**Server:** https://thika-technical-academic-management.onrender.com  
**Prepared for:** System Administrator / ICT Staff  
**Date:** June 2026

---

## TABLE OF CONTENTS

1. [Overview of the System](#1-overview)
2. [What You Need Before Starting](#2-prerequisites)
3. [Step 1 — Physical Installation of the Scanner](#3-physical-installation)
4. [Step 2 — Connect Scanner to the Network](#4-network-setup)
5. [Step 3 — Access the Scanner's Web Admin Panel](#5-scanner-web-admin)
6. [Step 4 — Configure the API Callback URL](#6-api-callback)
7. [Step 5 — Register the Scanner in Super Admin](#7-super-admin-registration)
8. [Step 6 — Enrol Trainee Fingerprints (Dept Admin)](#8-fingerprint-enrolment)
9. [Step 7 — Run Biometric Attendance Sessions (Trainer)](#9-attendance-sessions)
10. [Environment Variables Required on Render](#10-environment-variables)
11. [How the System Works (Technical Flow)](#11-technical-flow)
12. [Troubleshooting](#12-troubleshooting)
13. [Quick Reference — All URLs](#13-quick-reference)

---

## 1. OVERVIEW

The TTTI biometric system connects physical Suprema **BioEntry W** fingerprint scanners
to the online academic management system. Once set up:

- **Super Admin** registers each physical scanner device and assigns it to a room.
- **Dept Admin** enrols trainee fingerprints — linking each trainee's finger to their
  admission number in the system.
- **Trainer** starts a biometric attendance session — the scanner captures fingerprints
  and the system marks attendance automatically.

The scanner communicates with the server over HTTPS using a secure API callback.

```
┌─────────────────┐   fingerprint scan    ┌──────────────────────────────────┐
│  BioEntry W     │ ──── HTTPS POST ────► │  TTTI System (Render.com)        │
│  Scanner        │                       │  /biometric/api/attendance       │
│  (in classroom) │ ◄─── HTTP 200 ──────  │  /biometric/api/enroll           │
└─────────────────┘                       └──────────────────────────────────┘
```

---

## 2. PREREQUISITES

Before you begin, have the following ready:

| Item | Details |
|---|---|
| BioEntry W scanner(s) | Suprema BioEntry W or BioEntry W2 device |
| Power supply | PoE switch OR 12V DC adapter |
| Network cable | CAT5e or CAT6 ethernet cable |
| Internet connection | The scanner MUST have internet access to reach Render.com |
| A laptop / PC | To access the scanner web admin at `http://169.254.85.17` |
| Scanner serial number | Printed on the label on the back of the device |
| Super Admin login | https://thika-technical-academic-management.onrender.com |
| `BIOMETRIC_DEVICE_SECRET` | A secret key configured on Render and on the device |

> **Important:** The Render server is publicly accessible on HTTPS port 443.  
> The BioEntry W scanner only needs **outbound** internet access (port 443).  
> No port-forwarding or static public IP is required at TTTI.

---

## 3. STEP 1 — PHYSICAL INSTALLATION OF THE SCANNER

### 3.1 Mounting Location
- Mount the scanner at **entry/exit point** of the classroom, workshop, or lab.
- Recommended height: **100–120 cm** from the floor (comfortable for fingerprint placement).
- Keep away from direct sunlight and excessive dust.
- Ensure a power source is within reach (PoE switch port or 12V DC outlet).

### 3.2 Power Connection

**Option A — Power over Ethernet (PoE):**
1. Connect a standard CAT6 cable from the scanner's RJ45 port to a **PoE-capable switch port**.
2. The scanner powers on automatically — the LED indicator will glow.

**Option B — DC Power Adapter:**
1. Connect the 12V DC adapter to the scanner's power input.
2. Connect a separate CAT6 cable from the scanner's RJ45 port to any switch port.

### 3.3 Confirm Power-On
- The scanner displays a **blue/white LED** and shows the Suprema logo on screen.
- Wait 30–60 seconds for the device to fully boot.

---

## 4. STEP 2 — CONNECT SCANNER TO THE NETWORK

### 4.1 Scanner IP Address
The TTTI BioStar fingerprint scanner is configured at:

> **Scanner IP Address: `169.254.85.17`**

This is a **link-local address** (APIPA range `169.254.x.x`). This means:
- The scanner is directly reachable on the local network segment.
- No DHCP server or router is required between your laptop and the scanner for initial setup.
- For the scanner to send data to the Render.com server, it **must** also have internet access through the building's network gateway.

| Setting | Value |
|---|---|
| **Scanner IP** | `169.254.85.17` |
| **Subnet Mask** | `255.255.0.0` |
| **Default Admin Password** | `1234` (change immediately) |

### 4.2 Connect to the Scanner Web Admin
1. Connect your laptop to the **same network** as the scanner (same switch or direct cable).
2. Set your laptop's IP address to the same link-local range:
   - **Laptop IP:** `169.254.85.50` (or any `169.254.x.x` address other than `.17`)
   - **Subnet Mask:** `255.255.0.0`
3. Open a browser and navigate to:
   ```
   http://169.254.85.17
   ```
4. You should see the BioStar / BioEntry W login page.

> **Tip:** On Windows, go to **Control Panel → Network & Sharing → Change adapter settings → Ethernet → Properties → IPv4 → Use the following IP address** and enter the values above. Remember to restore to automatic (DHCP) afterwards.

### 4.3 Assign a Static IP (Recommended for Production)
The link-local address (`169.254.85.17`) is suitable for initial setup. For a permanent deployment, set a static IP in your building's proper subnet so the scanner can also reach the internet:

1. Log in to the scanner web admin at `http://169.254.85.17` (user: `admin`, password: `1234`).
2. Go to **Network → TCP/IP Settings**.
3. Set **IP Assignment** to `Static`.
4. Enter an IP in your building's network range (e.g., `192.168.10.50`), your router's subnet mask, and gateway.
5. Set **DNS Server** to `8.8.8.8` (Google) or your router's IP.
6. Click **Apply** — the scanner will reboot with the new address.

> If you keep using `169.254.85.17`, ensure that the switch port the scanner is connected to also has a route to the internet (so callbacks to Render.com can succeed).

### 4.4 Test Internet Access
From the scanner's **Network Diagnostics** page, test connectivity to:
```
thika-technical-academic-management.onrender.com
```
A successful ping confirms the scanner can reach the TTTI server over the internet.

---

## 5. STEP 3 — ACCESS THE SCANNER'S WEB ADMIN PANEL

1. Open a browser on a PC connected to the same network as the scanner.
2. Navigate to the scanner's IP address:
   ```
   http://169.254.85.17
   ```
   *(If you reassigned a new static IP in Step 4.3, use that address instead.)*
3. Log in:
   - **Username:** `admin`
   - **Password:** `1234` (or whatever you changed it to)
4. You are now in the BioStar / BioEntry W web admin interface.

> **Security:** Change the default password immediately under **System → Administrator**.

---

## 6. STEP 4 — CONFIGURE THE API CALLBACK URL

This is the most critical step. You must tell the scanner where to send fingerprint
data when a scan occurs.

### 6.1 Set the Server URL

In the BioEntry W web admin panel:

1. Go to **Server → BioStar 2 Server Settings** OR **Network → Server**.
2. Look for **"Event Notification"** or **"HTTP Push Event"** settings.
3. Enable **HTTP Push Events**.
4. Set the **Server URL / Callback URL** fields as follows:

| Event Type | URL to enter |
|---|---|
| **Attendance / Access Event** | `https://thika-technical-academic-management.onrender.com/biometric/api/attendance` |
| **Enrolment Event** | `https://thika-technical-academic-management.onrender.com/biometric/api/enroll` |

5. Set **HTTP Method** to `POST`.
6. Set **Content-Type** to `application/json`.

### 6.2 Set the Device Secret Key

The TTTI system requires a shared secret to authenticate that requests are coming
from a legitimate scanner (not an impersonator).

1. In the scanner web admin, find the **Custom Header** or **Authorization** field.
2. Add a header:
   - **Header Name:** `X-Device-Secret`
   - **Header Value:** *(the secret key — get this from the Render environment variables)*

> See Section 10 for how to find/set the `BIOMETRIC_DEVICE_SECRET` on Render.

### 6.3 Set the Device ID

1. In the scanner web admin, find **Device ID** or **Device Serial Number**.
2. Note this value — it should match exactly what you registered in the Super Admin
   scanner registry (see Step 5).

### 6.4 Save and Reboot
Click **Apply / Save**, then reboot the scanner via **System → Reboot**.

---

## 7. STEP 5 — REGISTER THE SCANNER IN SUPER ADMIN

> **URL:** https://thika-technical-academic-management.onrender.com/super-admin/biometric-scanners

### 7.1 Login as Super Admin
1. Go to https://thika-technical-academic-management.onrender.com
2. Log in with your Super Admin credentials.
3. In the left sidebar, under **Biometric System**, click **Scanner Registration**.

### 7.2 Register the Scanner
Fill in the **Register New Scanner** form on the left:

| Field | What to enter | Example |
|---|---|---|
| **Device Serial / ID** *(required)* | The serial number from the scanner label or device admin panel | `BWXK-20240801-001` |
| **Device Name / Label** | A friendly name for the scanner | `Workshop A Fingerprint Scanner` |
| **Room / Location** *(required)* | The exact room this scanner is installed in | `Workshop A` |
| **Building** | Building name or block | `Block B` |
| **Department** | Select the department this room belongs to | `Mechanical Engineering` |
| **Notes** | Any relevant installation info | `Installed June 2026, PoE port 3` |

Click **Register Scanner**.

### 7.3 Verify Registration
The scanner now appears in the **Registered Scanners** table with status **Active**.
- You can edit the room assignment at any time using the **Edit** button.
- Use **Remove** to decommission a scanner.

---

## 8. STEP 6 — ENROL TRAINEE FINGERPRINTS (DEPT ADMIN)

> **URL:** https://thika-technical-academic-management.onrender.com/dept-admin/fingerprint-registration

Before attendance can be taken biometrically, each trainee's fingerprint must be
enrolled and linked to their admission number in the system.

### 8.1 Login as Dept Admin / HOD
1. Log in with the department admin account.
2. In the left sidebar, click **Fingerprint Registration**.

### 8.2 The Registration Page
You will see:
- A **stats strip** showing total trainees, registered (have fingerprint ID), and not registered.
- A **filter bar** to filter by class or search by name.
- A **trainees table** listing all students in your department.

### 8.3 Method A — Live Enrolment (BioEntry W Scanner)
This method uses the physical scanner to capture the fingerprint in real time.

1. Have the trainee **present at the scanner** (physically standing in front of it).
2. In the trainees table, find the trainee and click **Live Enroll**.
3. The system creates a **waiting session** — the scanner is now listening.
4. Ask the trainee to **place their finger** on the scanner sensor.
5. The scanner captures the fingerprint, sends it to the server, and the system
   automatically links the fingerprint ID to the trainee's record.
6. The page polls every 2 seconds — when successful, the row updates to show
   **Registered** with the biometric ID badge.
7. The session times out after **3 minutes** if no finger is placed.

> The screen shows a **pulsing amber banner** while waiting, turns **green** on success,
> and **red** on error.

### 8.4 Method B — Manual ID Assignment
If you already know the trainee's biometric ID (from BioStar 2 software or a previous system):

1. In the trainee's row, click **Manual**.
2. A small form appears — enter the **Fingerprint ID** number.
3. Click **Assign**.
4. The row updates immediately.

### 8.5 Removing a Fingerprint
To clear a trainee's fingerprint registration (e.g., device replaced, re-enrol):
1. Click **Remove** on the trainee's row.
2. Confirm the removal.
3. The biometric ID is cleared from the system. The trainee can be re-enrolled.

---

## 9. STEP 7 — RUN BIOMETRIC ATTENDANCE SESSIONS (TRAINER)

> **URL:** https://thika-technical-academic-management.onrender.com/biometric/

### 9.1 Login as Trainer
1. Log in with the trainer account.
2. In the left sidebar, click **Biometric Attendance** (or navigate to `/biometric/`).

### 9.2 Start an Attendance Session
1. Click **Start Biometric Session**.
2. Select:
   - **Class** — the class you are taking attendance for.
   - **Unit** — the subject/unit for this lesson.
   - **Room / Scanner** — select the scanner installed in your room.
3. Click **Begin Session**.
4. The session is now **live** — the scanner in the selected room is active.

### 9.3 Taking Attendance
1. As trainees arrive, they **place their finger** on the scanner.
2. The system identifies the fingerprint, matches it to a registered trainee, and
   marks them **Present** instantly.
3. The trainer's screen updates in real time (polling every 2 seconds) showing:
   - A live list of who has been marked present.
   - Count of present vs total enrolled.
4. Trainees who do not scan are automatically marked **Absent** when the session ends.

### 9.4 End the Session
1. Click **End Session** when the lesson is complete.
2. The system finalises the attendance record.
3. A summary is shown — present count, absent count, and any errors.
4. The attendance record is saved and visible to the student, trainer, and admin.

---

## 10. ENVIRONMENT VARIABLES REQUIRED ON RENDER

Log in to your **Render Dashboard** → select the TTTI service → **Environment** tab.

Ensure these variables are set:

| Variable Name | Description | Example Value |
|---|---|---|
| `BIOMETRIC_DEVICE_SECRET` | Shared secret between the scanner and server. Must match the `X-Device-Secret` header set in the scanner's web admin. | `ttti-bio-2026-xK9mP3` |
| `APP_BASE_URL` | The full public URL of the deployment. Used in clearance certificate QR codes. | `https://thika-technical-academic-management.onrender.com` |

### How to set `BIOMETRIC_DEVICE_SECRET`:
1. Go to **Render Dashboard** → your service → **Environment**.
2. Click **Add Environment Variable**.
3. Name: `BIOMETRIC_DEVICE_SECRET`
4. Value: Choose a long random string (e.g., `ttti-bio-2026-xK9mP3qR8`).
5. Click **Save Changes** — Render will redeploy automatically.
6. Go back to the **BioEntry W web admin panel** and set the same value as the
   `X-Device-Secret` HTTP header in the callback settings.

> **Keep this secret private.** Anyone who knows this value can fake attendance records.

---

## 11. HOW THE SYSTEM WORKS (TECHNICAL FLOW)

### Fingerprint Enrolment Flow
```
Dept Admin clicks "Live Enroll"
        │
        ▼
System creates active_enrollment session in memory
(student_id, dept_id, status="waiting")
        │
        ▼
Trainee places finger on BioEntry W
        │
        ▼
BioEntry W sends POST to:
  /biometric/api/enroll
  Headers: X-Device-Secret: <secret>
  Body:    { "device_id": "BWXK-...", "biometric_id": "12345", "timestamp": "..." }
        │
        ▼
Server validates secret, finds waiting session,
saves biometric_id to user_profiles.biometric_id
Sets session status = "done"
        │
        ▼
Dept Admin page polls /biometric/enroll-status every 2s
Sees "done" → updates UI → shows Registered badge
```

### Biometric Attendance Flow
```
Trainer starts session (class + unit + scanner selected)
        │
        ▼
System stores active_session in DB with status="open"
        │
        ▼
Trainee places finger on BioEntry W
        │
        ▼
BioEntry W sends POST to:
  /biometric/api/attendance
  Headers: X-Device-Secret: <secret>
  Body:    { "device_id": "BWXK-...", "biometric_id": "12345", "timestamp": "..." }
        │
        ▼
Server looks up biometric_id → finds trainee in user_profiles
Checks if trainee is enrolled in the active session's class
Marks attendance record as "present"
        │
        ▼
Trainer's screen polls every 2s → shows trainee marked present
```

---

## 12. TROUBLESHOOTING

### Scanner not connecting to server

| Symptom | Likely Cause | Fix |
|---|---|---|
| Scanner shows "Server Unreachable" | No internet access | Check network cable and that the switch port at `169.254.85.17` has a route to the internet. Verify DNS is `8.8.8.8`. |
| 401 Unauthorized response | Wrong `X-Device-Secret` | Make sure the header value matches `BIOMETRIC_DEVICE_SECRET` on Render exactly |
| 404 Not Found | Wrong callback URL | Double-check the URL — no trailing slash, correct path `/biometric/api/attendance` |
| 500 Server Error | Server issue | Check Render logs at dashboard.render.com |
| Session times out immediately | Render cold start | Free Render instances sleep after 15 min. First request after sleep takes 30–60s. Upgrade to a paid instance or ping the server first. |

### Fingerprint enrolment not working

| Symptom | Fix |
|---|---|
| Enrol session times out (3 min) | Ensure scanner is on and connected. Check that `X-Device-Secret` is correct. Check server logs for incoming POST requests. |
| "Biometric ID already assigned" | Remove the existing fingerprint first, then re-enrol |
| Trainee not appearing in list | Trainee must be enrolled in a class in this department |
| Live enrol button greyed out | Another enrolment session may be active. Wait or cancel the active session. |

### Attendance not being marked

| Symptom | Fix |
|---|---|
| Trainee scans but not marked present | Trainee may not have a biometric_id enrolled. Check their row in Dept Admin Fingerprint Registration. |
| Session shows 0 present after many scans | Check that the scanner's callback URL is set to the attendance endpoint, not the enrol endpoint |
| Wrong trainee marked present | Two trainees enrolled with the same biometric_id — remove and re-enrol the incorrect one |

### Render cold start (free tier)
The Render free tier **spins down** after 15 minutes of inactivity. The first request
after a cold start takes **30–60 seconds**. During this time the scanner's callback
may time out and drop the event.

**Solution:** Upgrade to a paid Render plan (Starter $7/month) to keep the instance
always running. Alternatively, use a service like UptimeRobot to ping the server
every 10 minutes to prevent sleeping.

---

## 13. QUICK REFERENCE — ALL URLs

| Role | Feature | URL |
|---|---|---|
| Super Admin | Register / manage scanners | https://thika-technical-academic-management.onrender.com/super-admin/biometric-scanners |
| Dept Admin | Enrol trainee fingerprints | https://thika-technical-academic-management.onrender.com/dept-admin/fingerprint-registration |
| Trainer | Biometric attendance sessions | https://thika-technical-academic-management.onrender.com/biometric/ |
| Device → Server | Enrolment callback (POST) | https://thika-technical-academic-management.onrender.com/biometric/api/enroll |
| Device → Server | Attendance callback (POST) | https://thika-technical-academic-management.onrender.com/biometric/api/attendance |
| Public | Clearance serial verification | https://thika-technical-academic-management.onrender.com/clearance/verify |

---

## SUMMARY CHECKLIST

Use this checklist when setting up a new scanner:

- [ ] Scanner physically mounted and powered on
- [ ] Scanner connected to internet via network cable
- [ ] Scanner web admin accessed at `http://169.254.85.17` (laptop IP set to `169.254.85.50 / 255.255.0.0`)
- [ ] Admin password changed from default `1234`
- [ ] Static IP confirmed or reassigned (current: `169.254.85.17`)
- [ ] DNS set to `8.8.8.8`
- [ ] Internet connectivity tested from scanner
- [ ] Attendance callback URL set: `.../biometric/api/attendance`
- [ ] Enrolment callback URL set: `.../biometric/api/enroll`
- [ ] `X-Device-Secret` header set on scanner (matches Render env var)
- [ ] `BIOMETRIC_DEVICE_SECRET` set on Render environment
- [ ] Scanner registered in Super Admin with correct serial, room, and department
- [ ] At least one trainee fingerprint enrolled via Dept Admin
- [ ] Test attendance session run by trainer — fingerprint recognised correctly

---

*Document prepared for TTTI ICT Department — June 2026*  
*System: TTTI Academic Management System (thika-technical-academic-management.onrender.com)*
