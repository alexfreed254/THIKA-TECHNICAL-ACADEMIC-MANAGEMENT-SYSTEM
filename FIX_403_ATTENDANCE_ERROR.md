# Fix: 403 Access Denied - Mark Attendance

## Problem
When clicking "Mark Attendance" in trainer dashboard, you get:
```
403 — Access Denied
You don't have permission to view this page.
```

## Root Cause
The logged-in user's role in the database is **NOT** "trainer". The Mark Attendance page requires the user to have role = "trainer".

## Solution

### Step 1: Check Your Current Role
1. Restart Flask application (to load updated error messages)
2. Try accessing Mark Attendance again
3. You will now see a helpful message like:
   ```
   Access denied. Your role 'dept_admin' does not have permission to access this page. Required role(s): trainer
   ```

### Step 2: Update Your Role in Database

#### Option A: Using Supabase Dashboard (Recommended)
1. Open Supabase Dashboard
2. Go to **Table Editor**
3. Select **user_profiles** table
4. Find your user (search by email or name)
5. Click on the **role** field
6. Change it to: **trainer**
7. Save

#### Option B: Using SQL
```sql
-- Replace 'your-email@example.com' with your actual email
UPDATE user_profiles 
SET role = 'trainer' 
WHERE email = 'your-email@example.com';
```

### Step 3: Logout and Login Again
1. Click **Sign Out**
2. Login again
3. Your session will now have the updated role
4. Mark Attendance should now work!

---

## Valid Roles in the System

| Role | Description |
|------|-------------|
| `super_admin` | Full system access |
| `dept_admin` | Department administrator |
| **`trainer`** | **Trainer (required for Mark Attendance)** |
| `student` | Student/trainee |
| `employer` | Company/employer |
| `examination_officer` | Examination officer |
| `industry_mentor` | Industry supervisor |
| `internal_verifier` | Internal verifier |
| `sports_hod` | Sports HOD |
| `environment_hod` | Environment HOD |
| `dean_students` | Dean of students |
| `library_hod` | Library HOD |
| `finance_officer` | Finance officer |
| `registrar` | Registrar |
| `deputy_principal` | Deputy principal |
| `quality_assurance_officer` | QA officer |
| `workshop_technician` | Workshop technician |
| `liaison_officer` | Liaison officer |
| `cdacc_verifier` | CDACC verifier |
| `industry_supervisor` | Industry supervisor |

---

## What Pages Require "Trainer" Role?

The following pages require role = "trainer":
- ✅ Mark Attendance (`/trainer/attendance`)
- ✅ View & Download Attendance (`/trainer/attendance-history`)
- ✅ Trainee POE Review (`/trainer/assessments`)
- ✅ Marks Entry (`/trainer/marks-entry`)
- ✅ Import Marks (`/trainer/marks-import`)
- ✅ My Portfolio (`/trainer/portfolio`)
- ✅ Upload Trip Report (`/academic-trips/upload`)
- ✅ All other `/trainer/*` pages

---

## Alternative: Allow Your Current Role

If you want to keep your current role but still access trainer pages, you can modify the role requirements:

### For Super Admins:
Super admins should already have access to most pages. If not, update decorators:

```python
# In routes/trainer.py
@trainer_bp.route("/attendance", methods=["GET", "POST"])
@role_required("trainer", "super_admin")  # Allow both
def attendance():
    # ...
```

### For Department Admins:
If dept_admins should mark attendance:

```python
# In auth_utils.py
def trainer_required(f):
    return role_required("trainer", "dept_admin")(f)
```

⚠️ **Warning:** This changes system-wide behavior. Only do this if you understand the implications.

---

## Testing After Fix

1. **Logout and Login**
2. **Check Role:**
   - Go to Profile page
   - Verify role is displayed correctly

3. **Test Mark Attendance:**
   - Navigate to: Trainer Dashboard → Mark Attendance
   - Should load without 403 error
   - Should show attendance form

4. **Test Other Pages:**
   - Try all trainer menu items
   - All should work now

---

## Still Getting 403?

### Check These:

1. **Did you logout/login after changing role?**
   - Session caches the old role
   - Must logout and login to refresh

2. **Is Flask restarted?**
   - Restart Flask to load error message improvements
   - You should see which role is required

3. **Check database:**
   ```sql
   SELECT email, full_name, role 
   FROM user_profiles 
   WHERE email = 'your-email@example.com';
   ```

4. **Check session:**
   - Open browser DevTools (F12)
   - Go to Application → Cookies
   - Clear session cookie
   - Login again

---

## Improved Error Messages

After this fix, when you get a 403 error, you'll see:

**Before:**
```
403 — Access Denied
You don't have permission to view this page.
```

**After:**
```
403 — Access Denied
Access denied. Your role 'dept_admin' does not have permission to access 
this page. Required role(s): trainer
```

This makes it much easier to diagnose permission issues!

---

## Summary

**Problem:** User role is not "trainer"
**Solution:** Update user role to "trainer" in database
**Steps:**
1. Check current role (error message will show it now)
2. Update role in Supabase to "trainer"
3. Logout and login again
4. Test Mark Attendance

**Time to Fix:** 2 minutes

---

**Changes Pushed to GitHub:** ✅ Commit 55b35f7
**Status:** Ready to test

Try accessing Mark Attendance now - you should see a helpful error message showing your current role!
