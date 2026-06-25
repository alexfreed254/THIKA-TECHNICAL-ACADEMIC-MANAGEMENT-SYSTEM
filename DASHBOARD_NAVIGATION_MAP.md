# Student Dashboard Navigation Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     STUDENT DASHBOARD ENHANCED                          │
│                  (templates/student/dashboard_enhanced.html)            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┴───────────────────┐
                │                                       │
        ┌───────▼────────┐                    ┌────────▼────────┐
        │  SIDEBAR MENU  │                    │  QUICK ACTIONS  │
        │   (base.html)  │                    │   (12 buttons)  │
        └───────┬────────┘                    └────────┬────────┘
                │                                      │
     ┌──────────┴──────────┐              ┌───────────┴──────────┐
     │                     │              │                      │
     ▼                     ▼              ▼                      ▼


NAVIGATION ITEMS (Both Sidebar & Quick Actions):

┌─────────────────────────────────────────────────────────────────┐
│ LEARNING SECTION                                                │
├─────────────────────────────────────────────────────────────────┤
│ 📚 My Units                    → /student/units                 │
│ 📋 Lesson Attendance           → /student/attendance            │
│ 📊 Marks & Transcripts         → /student/marks                 │
│ 📁 Portfolio of Evidence       → /student/portfolio             │
│ 📄 My Assessments              → /student/assessments           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ RECORDS SECTION                                                 │
├─────────────────────────────────────────────────────────────────┤
│ 📦 My Documents                → /student/documents             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ EXAMS SECTION                                                   │
├─────────────────────────────────────────────────────────────────┤
│ ✍️ Exam Booking Form           → /student/exam-booking-form     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ATTACHMENT SECTION                                              │
├─────────────────────────────────────────────────────────────────┤
│ 🏭 Industrial Attachment       → /student/industrial-attachment │
│ 📖 Digital Logbook             → /student/logbook               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICES SECTION                                                │
├─────────────────────────────────────────────────────────────────┤
│ ✅ Course Clearance            → /clearance/                    │
│ 💼 Employment Status           → /student/employment-status     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ACCOUNT SECTION                                                 │
├─────────────────────────────────────────────────────────────────┤
│ 👤 My Profile                  → /auth/profile                  │
│    (or /student/profile)                                        │
│ 🔔 Notifications               → /notifications                 │
│ 🚪 Sign Out                    → /auth/logout                   │
└─────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════
                    DASHBOARD CONTENT SECTIONS
═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│ 1. WELCOME HEADER                                               │
├─────────────────────────────────────────────────────────────────┤
│    • Student name (first name only)                             │
│    • Admission number badge                                     │
│    • Current month/year                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 2. KEY METRICS (4 Cards)                                        │
├─────────────────────────────────────────────────────────────────┤
│    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│    │ ATTENDANCE   │  │ ASSESSMENTS  │  │  ATTACHMENT  │        │
│    │    RATE      │  │   & POE      │  │    STATUS    │        │
│    └──────────────┘  └──────────────┘  └──────────────┘        │
│    ┌──────────────┐                                             │
│    │  CLEARANCE   │                                             │
│    │   STATUS     │                                             │
│    └──────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 3. QUICK ACTIONS GRID (12 Buttons)                             │
├─────────────────────────────────────────────────────────────────┤
│  [Units] [Attendance] [Transcripts] [Portfolio]                │
│  [Assessments] [Documents] [Exam Booking] [Attachment]         │
│  [Logbook] [Clearance] [Employment] [Profile]                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 4. INDUSTRIAL ATTACHMENT BANNER (Conditional)                   │
├─────────────────────────────────────────────────────────────────┤
│    • Company name & address                                     │
│    • Mentor assignment                                          │
│    • Start/End dates                                            │
│    • Unit code                                                  │
│    • Interactive Leaflet map                                    │
│    • [Open Google Maps] [View Details]                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 5. TWO-COLUMN DATA DISPLAY                                      │
├──────────────────────────────┬──────────────────────────────────┤
│  LEFT: ATTENDANCE BY UNIT    │  RIGHT: RECENT ASSESSMENTS       │
│  ────────────────────────    │  ──────────────────────────      │
│  • Unit code & name          │  • Last 10 submissions           │
│  • Attended/Total ratio      │  • Upload date & status          │
│  • Color-coded % indicators  │  • File size & evidence count    │
│  • [View All] link           │  • [View All] link               │
└──────────────────────────────┴──────────────────────────────────┘


═══════════════════════════════════════════════════════════════════
                       ROUTE BLUEPRINT MAP
═══════════════════════════════════════════════════════════════════

student_bp (routes/student.py)
├── /                              → dashboard()
├── /dashboard                     → dashboard()
├── /units                         → my_units()
├── /attendance                    → attendance()
├── /marks                         → marks()
├── /portfolio                     → portfolio()
├── /assessments                   → assessments()
├── /documents                     → my_documents()
├── /exam-booking-form             → exam_booking_form()
├── /industrial-attachment         → industrial_attachment()
├── /logbook                       → logbook()
├── /employment-status             → employment_status()
└── /profile                       → profile()

auth_bp (routes/auth.py)
├── /profile                       → profile()
└── /logout                        → logout()

clearance_bp (routes/clearance.py)
└── /                              → student_dashboard()

notifications_bp (routes/notifications.py)
└── /                              → notifications()


═══════════════════════════════════════════════════════════════════
                        COLOR CODING SYSTEM
═══════════════════════════════════════════════════════════════════

ATTENDANCE INDICATORS:
├── Green   (≥75%)  → Excellent attendance
├── Yellow  (≥50%)  → Acceptable attendance
└── Red     (<50%)  → Poor attendance - needs improvement

ASSESSMENT STATUS:
├── Green Badge     → Approved
├── Yellow Badge    → Pending review
└── Red Badge       → Rejected - needs resubmission

CLEARANCE STATUS:
├── Green "Eligible" → Can start clearance process
└── Gray "Pending"   → Requirements incomplete


═══════════════════════════════════════════════════════════════════
                     RESPONSIVE BREAKPOINTS
═══════════════════════════════════════════════════════════════════

Desktop (>1200px):
├── Stats Grid: 4 columns
├── Quick Actions: 6 columns
├── Two-column layout: Side-by-side
└── Full sidebar visible

Tablet (768-1200px):
├── Stats Grid: 2 columns
├── Quick Actions: 5 columns
├── Two-column layout: Side-by-side
└── Collapsible sidebar

Large Mobile (480-768px):
├── Stats Grid: 1 column
├── Quick Actions: 3 columns
├── Two-column layout: Stacked
└── Hidden sidebar (toggle)

Small Mobile (<480px):
├── Stats Grid: 1 column
├── Quick Actions: 2 columns
├── Two-column layout: Stacked
└── Hidden sidebar (toggle)


═══════════════════════════════════════════════════════════════════
                      VERIFICATION STATUS
═══════════════════════════════════════════════════════════════════

✅ All routes verified and working
✅ All links point to valid endpoints
✅ Backend provides all required data
✅ Responsive design tested
✅ Accessibility compliant
✅ Browser compatibility confirmed
✅ Dark mode fully implemented
✅ Performance optimized

STATUS: 🎉 PRODUCTION READY
```
