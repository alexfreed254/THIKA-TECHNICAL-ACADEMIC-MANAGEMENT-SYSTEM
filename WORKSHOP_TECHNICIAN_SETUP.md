# Workshop Technician Dashboard - Setup Guide

## Overview
The Workshop Technician dashboard provides staff with tools to manage workshop inventory and approve trainee clearances within their assigned department.

## Features

### 1. **Workshop Inventory Management**
- Add, edit, and delete inventory items
- Track equipment by category, condition, quantity, and location
- Monitor low stock items (quantity < 3)
- Track damaged/poor condition equipment
- Record maintenance dates and serial numbers
- Full search and filtering capabilities

### 2. **Clearance Approvals**
- Review pending clearance requests from trainees
- Approve or reject clearances with comments
- Filter by status (pending, approved, rejected)
- Track clearance history

---

## Database Setup

### Step 1: Run the Migration Script

Execute the SQL migration to create the workshop_inventory table:

```bash
# Run in Supabase SQL Editor:
```

Copy and execute the contents of `workshop_inventory_migration.sql` in your Supabase SQL Editor.

This migration will:
- Create the `workshop_inventory` table
- Add indexes for performance
- Update the `user_profiles` role constraint to include `workshop_technician`
- Set up automatic `updated_at` triggers

### Step 2: Verify the Migration

Run this query to verify:

```sql
-- Check if workshop_inventory table exists
SELECT 
    'workshop_inventory table created' AS status,
    COUNT(*) AS record_count 
FROM workshop_inventory;

-- List all workshop technicians
SELECT 
    id,
    full_name,
    email,
    staff_no,
    department_id,
    created_at
FROM user_profiles
WHERE role = 'workshop_technician'
ORDER BY created_at DESC;
```

---

## Creating Workshop Technician Users

### Method 1: Using Super Admin Dashboard

1. Login as **Super Admin**
2. Navigate to **Users** or **Manage Staff**
3. Click **Add User** or **Create Staff Member**
4. Fill in the form:
   - **Email**: Staff email address
   - **Full Name**: Staff member's full name
   - **Role**: Select `workshop_technician`
   - **Department**: Assign to specific department (e.g., Mechanical, Electrical)
   - **Staff Number**: Optional staff ID
   - **Password**: Set initial password (staff will change on first login)

### Method 2: Using SQL (Direct Insert)

```sql
-- First, create the auth user
INSERT INTO auth.users (
    id,
    email,
    encrypted_password,
    email_confirmed_at,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),
    'workshop.tech@thikatechnical.ac.ke',
    crypt('ChangeMe123!', gen_salt('bf')),
    NOW(),
    NOW(),
    NOW()
)
RETURNING id;

-- Then create the user profile (use the ID from above)
INSERT INTO user_profiles (
    id,  -- Use the UUID from auth.users insert
    email,
    full_name,
    role,
    department_id,
    staff_no,
    is_active,
    must_change_password
)
VALUES (
    '<UUID_FROM_AUTH_USERS>',
    'workshop.tech@thikatechnical.ac.ke',
    'John Doe',
    'workshop_technician',
    (SELECT id FROM departments WHERE code = 'MECH' LIMIT 1),  -- Assign to Mechanical dept
    'WT001',
    true,
    true  -- Force password change on first login
);
```

---

## Login Instructions for Workshop Technicians

### Step 1: Navigate to Login Page
Open your browser and go to: `https://your-domain.com/auth/login`

### Step 2: Select Staff Login
- Select **Staff Login** tab
- Enter your **Email** and **Password**
- Click **Sign In**

### Step 3: First Time Login
If `must_change_password` is set to `true`:
- You'll be prompted to change your password
- Set a strong password (minimum 8 characters, 1 number, 1 symbol)

### Step 4: Access Dashboard
After successful login, you'll be redirected to: `/workshop-technician/dashboard`

---

## Using the Workshop Technician Dashboard

### Dashboard Overview
The main dashboard displays:
- **Total inventory items** in your department
- **Low stock items** (quantity < 3)
- **Poor/Damaged equipment** count
- **Pending clearances** count
- **Recently added items** list
- **Quick access links** to key features

### Managing Inventory

#### Adding New Items
1. Navigate to **Workshop Inventory**
2. Click **+ Add Item** button
3. Fill in the form:
   - **Item Name** (required): e.g., "Angle Grinder 4½ inch"
   - **Category**: Select from dropdown
   - **Quantity**: Number in stock
   - **Condition**: good, fair, poor, or damaged
   - **Serial Number**: Equipment tag/serial
   - **Location**: Workshop location (e.g., "Shelf A3")
   - **Last Serviced**: Maintenance date
   - **Description**: Brief details
   - **Notes**: Maintenance notes or issues
4. Click **Save Item**

#### Editing Items
1. Find the item in the inventory list
2. Click **Edit** button
3. Update the fields
4. Click **Update Item**

#### Deleting Items
1. Find the item in the inventory list
2. Click **Delete** button
3. Confirm deletion

#### Searching & Filtering
- **Search bar**: Search by item name, serial number, description, or location
- **Category filter**: Filter by equipment category
- **Condition filter**: Filter by equipment condition
- **Quick filters**: 
  - Click "Damaged Items" for quick access to equipment needing attention

### Managing Clearances

#### Viewing Clearance Requests
1. Navigate to **Clearance Approvals**
2. View all requests assigned to you
3. Filter by status:
   - **All**: View all clearance requests
   - **Pending**: Requests awaiting your action
   - **Approved**: Requests you've approved
   - **Rejected**: Requests you've rejected

#### Approving Clearances
1. Find the pending clearance request
2. Review trainee information and stage details
3. Click **Approve** button
4. Confirm approval

#### Rejecting Clearances
1. Find the pending clearance request
2. Click **Reject** button
3. Enter the **reason for rejection** (required)
4. Click **Confirm Rejection**

**Note**: Trainees will be notified of your decision.

---

## Inventory Categories

The system supports the following categories:
- Power Tools
- Hand Tools
- Safety Equipment
- Measuring Instruments
- Electrical Equipment
- Machinery
- Computer / ICT Equipment
- Furniture / Fixtures
- Consumables
- Other

---

## Equipment Conditions

Track equipment in four condition states:
- **Good**: Fully functional, no issues
- **Fair**: Functional with minor wear
- **Poor**: Needs repair or maintenance
- **Damaged**: Not functional, requires significant repair

---

## Notifications

Workshop Technicians receive notifications for:
- New clearance requests assigned
- Low stock alerts (when quantity < 3)
- Clearance approval deadlines

Access notifications via the **bell icon** in the top right corner.

---

## Best Practices

### Inventory Management
1. **Regular audits**: Update quantities monthly
2. **Condition tracking**: Update equipment condition after each use/inspection
3. **Maintenance logs**: Record all servicing in the notes field
4. **Serial tracking**: Always record serial numbers for accountability
5. **Location updates**: Keep location information current

### Clearance Processing
1. **Timely reviews**: Process clearances within 24-48 hours
2. **Clear comments**: Provide specific reasons when rejecting
3. **Equipment checks**: Verify trainees have returned all borrowed equipment
4. **Documentation**: Keep records of damaged or missing items

---

## Troubleshooting

### Issue: Cannot Login
**Solution**: 
- Verify you're using the correct email
- Check if your account is active (contact Super Admin)
- Ensure you're using **Staff Login** (not Student Login)

### Issue: Cannot See Inventory
**Solution**:
- Verify you're assigned to a department
- Check with Super Admin to ensure proper department assignment

### Issue: No Clearance Requests Visible
**Solution**:
- Clearances must be assigned to your user ID
- Contact Super Admin to configure clearance stages properly
- Check that you're assigned as an approver for your department

### Issue: Cannot Add/Edit Inventory
**Solution**:
- Ensure you have `workshop_technician` role
- Verify you're assigned to the correct department
- Check browser console for errors (F12)

---

## Technical Details

### Routes
- Dashboard: `/workshop-technician/dashboard`
- Inventory: `/workshop-technician/inventory`
- Clearances: `/workshop-technician/clearances`
- Profile: `/auth/profile`

### Database Tables
- **workshop_inventory**: Stores all inventory items
- **clearance_approvals**: Tracks clearance approvals
- **user_profiles**: User account information

### Permissions
Workshop Technicians can:
- ✅ View/add/edit/delete inventory in their department
- ✅ Approve/reject clearances assigned to them
- ✅ View their own profile and update password
- ❌ Cannot access other departments' inventory
- ❌ Cannot modify clearance requests from other approvers

---

## Support

For technical issues or questions:
1. Contact your **Department Admin**
2. Email the **System Administrator**
3. Refer to the main **SYSTEM_SUMMARY.md** documentation

---

## Changelog

### Version 1.0 (Current)
- Initial workshop technician dashboard
- Inventory management system
- Clearance approval workflow
- Responsive design for mobile access
- Real-time notifications
