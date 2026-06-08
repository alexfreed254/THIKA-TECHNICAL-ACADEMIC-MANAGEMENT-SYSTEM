"""
Workshop Technician Setup Verification Script
Run this to verify that workshop technician functionality is properly configured.
"""

import sys
from db import get_service_client

def check_database_table():
    """Verify workshop_inventory table exists."""
    print("\n[1] Checking workshop_inventory table...")
    try:
        db = get_service_client()
        result = db.table("workshop_inventory").select("id").limit(1).execute()
        print("    ✓ workshop_inventory table exists")
        return True
    except Exception as e:
        print(f"    ✗ workshop_inventory table NOT found: {e}")
        print("    → Run workshop_inventory_migration.sql in Supabase SQL Editor")
        return False


def check_user_profiles_role():
    """Verify workshop_technician role is allowed in user_profiles."""
    print("\n[2] Checking user_profiles role constraint...")
    try:
        db = get_service_client()
        # Try to query for workshop_technician role
        result = db.table("user_profiles").select("id, full_name, email, role").eq("role", "workshop_technician").execute()
        users = result.data or []
        
        if users:
            print(f"    ✓ workshop_technician role is valid ({len(users)} user(s) found)")
            for user in users:
                print(f"      - {user.get('full_name')} ({user.get('email')})")
        else:
            print("    ⚠ workshop_technician role is valid but no users found")
            print("    → Create workshop technician users via Super Admin dashboard")
        return True
    except Exception as e:
        print(f"    ✗ workshop_technician role NOT allowed: {e}")
        print("    → Run workshop_inventory_migration.sql to update role constraint")
        return False


def check_routes():
    """Verify workshop_technician routes are registered."""
    print("\n[3] Checking Flask routes...")
    try:
        from app import app
        from flask import url_for
        
        with app.test_request_context():
            routes = [
                ("workshop_technician.dashboard", "/workshop-technician/dashboard"),
                ("workshop_technician.inventory", "/workshop-technician/inventory"),
                ("workshop_technician.clearances", "/workshop-technician/clearances"),
            ]
            
            all_ok = True
            for endpoint, expected_path in routes:
                try:
                    path = url_for(endpoint)
                    if path == expected_path:
                        print(f"    ✓ {endpoint} → {path}")
                    else:
                        print(f"    ⚠ {endpoint} → {path} (expected {expected_path})")
                except Exception as e:
                    print(f"    ✗ {endpoint} NOT registered: {e}")
                    all_ok = False
            
            return all_ok
    except Exception as e:
        print(f"    ✗ Cannot check routes: {e}")
        return False


def check_auth_redirect():
    """Verify auth.py redirects workshop_technician to correct dashboard."""
    print("\n[4] Checking auth.py redirects...")
    try:
        with open("routes/auth.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if correct redirect exists
        correct_redirect = 'workshop_technician.dashboard'
        wrong_redirect = 'trainer.dashboard'
        
        if correct_redirect in content and 'elif role == "workshop_technician"' in content:
            if wrong_redirect in content and 'workshop_technician' in content[:content.find(correct_redirect)]:
                print(f"    ⚠ Found old redirect to {wrong_redirect}")
                print(f"    → But also found correct redirect to {correct_redirect}")
            else:
                print(f"    ✓ Redirects to workshop_technician.dashboard")
            return True
        else:
            print(f"    ✗ Does NOT redirect to workshop_technician.dashboard")
            print(f"    → Check routes/auth.py login function")
            return False
    except Exception as e:
        print(f"    ✗ Cannot check auth.py: {e}")
        return False


def check_templates():
    """Verify workshop_technician templates exist."""
    print("\n[5] Checking templates...")
    import os
    
    templates = [
        "templates/workshop_technician/base.html",
        "templates/workshop_technician/dashboard.html",
        "templates/workshop_technician/inventory.html",
        "templates/workshop_technician/clearances.html",
    ]
    
    all_ok = True
    for template in templates:
        if os.path.exists(template):
            print(f"    ✓ {template}")
        else:
            print(f"    ✗ {template} NOT found")
            all_ok = False
    
    return all_ok


def check_auth_utils():
    """Verify workshop_technician_required decorator exists."""
    print("\n[6] Checking auth_utils decorators...")
    try:
        from auth_utils import workshop_technician_required
        print("    ✓ workshop_technician_required decorator exists")
        return True
    except ImportError as e:
        print(f"    ✗ workshop_technician_required decorator NOT found: {e}")
        return False


def main():
    print("=" * 70)
    print("WORKSHOP TECHNICIAN SETUP VERIFICATION")
    print("=" * 70)
    
    results = []
    
    results.append(("Database Table", check_database_table()))
    results.append(("User Role Constraint", check_user_profiles_role()))
    results.append(("Flask Routes", check_routes()))
    results.append(("Auth Redirects", check_auth_redirect()))
    results.append(("Templates", check_templates()))
    results.append(("Auth Utils", check_auth_utils()))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status:10s} {name}")
    
    print(f"\nResult: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✓ All checks passed! Workshop Technician dashboard is ready to use.")
        print("\nNext steps:")
        print("  1. Run workshop_inventory_migration.sql if not already done")
        print("  2. Create workshop technician users via Super Admin")
        print("  3. Test login at /auth/login")
        return 0
    else:
        print("\n✗ Some checks failed. Please review the output above.")
        print("\nRefer to WORKSHOP_TECHNICIAN_SETUP.md for detailed setup instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
