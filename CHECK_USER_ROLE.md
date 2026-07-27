# Check User Role - Trainee Login Issue

## Problem
When logging in as trainee (student), user is redirected to department admin dashboard instead of student dashboard.

## Root Cause
The user's `role` field in the database is **NOT** set to "student". It's likely set to "dept_admin" or another role.

## How to Check

### Option 1: Check in Supabase Dashboard

1. Open **Supabase Dashboard**
2. Go to **Table Editor**
3. Click on **user_profiles** table
4. Find the trainee user by:
   - Search for their **admission_no** 
   - OR search for their **email**
5. Look at the **role** column
6. **Expected:** `student`
7. **If it shows something else:** That's the problem!

### Option 2: SQL Query

Run this query in Supabase SQL Editor:

```sql
-- Replace 'ADMISSION_NUMBER' with the actual admission number
SELECT 
    id,
    email,
    full_name,
    role,
    admission_no,
    is_active
FROM user_profiles 
WHERE admission_no = 'ADMISSION_NUMBER';
```

**Example:**
```sql
SELECT 
    id,
    email,
    full_name,
    role,
    admission_no,
    is_active
FROM user_profiles 
WHERE admission_no = 'TTI/2024/001';
```

### Check All Students

To see all users and their roles:

```sql
SELECT 
    admission_no,
    full_name,
    email,
    role,
    is_active
FROM user_profiles 
WHERE admission_no IS NOT NULL
ORDER BY admission_no;
```

---

## The Fix

### If role is wrong, update it:

```sql
-- Replace 'ADMISSION_NUMBER' with actual admission number
UPDATE user_profiles 
SET role = 'student' 
WHERE admission_no = 'ADMISSION_NUMBER';
```

**Example:**
```sql
UPDATE user_profiles 
SET role = 'student' 
WHERE admission_no = 'TTI/2024/001';
```

### Update Multiple Students at Once

If multiple students have wrong role:

```sql
-- Update all users with admission numbers to be students
UPDATE user_profiles 
SET role = 'student' 
WHERE admission_no IS NOT NULL 
  AND admission_no != ''
  AND role != 'student';
```

⚠️ **Warning:** This will change ALL non-student users who have admission numbers to be students. Use carefully!

---

## Why This Happens

### Common Scenarios:

1. **User was created as staff first, then given admission number**
   - User exists with role = "dept_admin" or "trainer"
   - Admission number was added later
   - Role was never updated to "student"

2. **Bulk import with wrong role**
   - CSV import had role column filled incorrectly
   - All students imported as "dept_admin" or another role

3. **Database migration issue**
   - Old data migrated with incorrect roles
   - Need to update roles after migration

4. **Manual creation error**
   - Admin created user with wrong role
   - Forgot to set role to "student"

---

## How Login Works

### Student Login Flow:

```
1. User enters admission number + password
2. System queries: 
   SELECT * FROM user_profiles 
   WHERE admission_no = 'XXX' 
     AND role = 'student'  ← MUST be student!
3. If found → Redirect to student.dashboard
4. If not found → Login fails
```

### The Problem:

If the user's role is "dept_admin":
```
1. User enters admission number + password
2. System queries for role = 'student'
3. Not found (because role is 'dept_admin')
4. Login might work anyway if they have both admission_no AND email
5. System checks their role
6. Role is 'dept_admin'
7. Redirects to dept_admin.dashboard ← WRONG!
```

---

## Testing After Fix

### Step 1: Update Role
```sql
UPDATE user_profiles 
SET role = 'student' 
WHERE admission_no = 'YOUR_ADMISSION_NO';
```

### Step 2: Verify Update
```sql
SELECT admission_no, role 
FROM user_profiles 
WHERE admission_no = 'YOUR_ADMISSION_NO';
```

Should show:
```
admission_no     | role
-----------------+--------
YOUR_ADMISSION_NO | student
```

### Step 3: Test Login

1. **Logout** completely (clear session)
2. **Login** using:
   - Login Type: **Trainee**
   - Admission Number: YOUR_ADMISSION_NO
   - Password: Your password
3. **Expected Result:** Redirect to `/student/dashboard`
4. **If still wrong:** Check again - role might not have been updated

---

## Bulk Fix Script

If you have many students with wrong roles:

```sql
-- Check how many are affected
SELECT 
    COUNT(*) as total_affected,
    role as current_role
FROM user_profiles 
WHERE admission_no IS NOT NULL 
  AND admission_no != ''
  AND role != 'student'
GROUP BY role;
```

This shows you how many users have admission numbers but aren't students.

**Then fix them:**

```sql
-- Backup first (optional but recommended)
CREATE TABLE user_profiles_backup AS 
SELECT * FROM user_profiles;

-- Update all to student
UPDATE user_profiles 
SET role = 'student' 
WHERE admission_no IS NOT NULL 
  AND admission_no != ''
  AND email NOT LIKE '%@staff.%'  -- Don't change staff emails
  AND role != 'student';

-- Verify
SELECT COUNT(*) 
FROM user_profiles 
WHERE role = 'student';
```

---

## Prevention

### When Creating New Students:

Always ensure:
```sql
INSERT INTO user_profiles (
    id, email, full_name, 
    role,           ← MUST be 'student'
    admission_no,   ← Required for students
    is_active,
    password_hash
) VALUES (
    uuid_generate_v4(),
    'student@example.com',
    'John Doe',
    'student',      ← SET THIS CORRECTLY
    'TTI/2024/001',
    true,
    '$2b$12$...'
);
```

### When Importing Students:

CSV should have:
```csv
email,full_name,admission_no,role,password_hash
student1@example.com,John Doe,TTI/2024/001,student,$2b$12$...
student2@example.com,Jane Smith,TTI/2024/002,student,$2b$12$...
```

**NOT:**
```csv
email,full_name,admission_no,role,password_hash
student1@example.com,John Doe,TTI/2024/001,dept_admin,$2b$12$...  ← WRONG
```

---

## Summary

**Problem:** Trainee redirected to dept_admin dashboard
**Root Cause:** User's `role` field is not "student"
**Solution:** Update role to "student" in database
**Check:** Run SQL query to see current role
**Fix:** UPDATE user_profiles SET role = 'student' WHERE admission_no = 'XXX'
**Test:** Logout, login again, should go to student dashboard

---

## Quick Fix Command

```sql
-- Single user fix
UPDATE user_profiles 
SET role = 'student' 
WHERE admission_no = 'TTI/2024/001';  -- Replace with actual admission number

-- Check if it worked
SELECT admission_no, full_name, email, role 
FROM user_profiles 
WHERE admission_no = 'TTI/2024/001';
```

**Expected output after fix:**
```
admission_no  | full_name | email              | role
--------------+-----------+--------------------+--------
TTI/2024/001  | John Doe  | john@example.com   | student
```

---

**Status:** Ready to fix
**Time to fix:** 2 minutes
**Difficulty:** Easy
**Risk:** Low (only changes role field)

Just run the SQL query and test login! 🚀
