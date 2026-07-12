#!/usr/bin/env python3
"""
Script to add Pride in Technology footer to all dashboard files.
Run this script to batch update all dashboard templates.
"""

import os
import re
from pathlib import Path

# Dashboard files to update
DASHBOARD_FILES = [
    "templates/trainer/dashboard.html",
    "templates/trainer/dashboard_enhanced.html",
    "templates/dept_admin/dashboard_enhanced.html",
    "templates/super_admin/welcome.html",
    "templates/industry_mentor/dashboard.html",
    "templates/industry_mentor/dashboard_enhanced.html",
    "templates/internal_verifier/dashboard.html",
    "templates/internal_verifier/dashboard_enhanced.html",
    "templates/examination_officer/dashboard.html",
    "templates/examination_officer/dashboard_enhanced.html",
    "templates/cdacc_verifier/dashboard.html",
    "templates/liaison_officer/dashboard.html",
    "templates/workshop_technician/dashboard.html",
    "templates/service_dept/dashboard.html",
    "templates/clearance/student_dashboard.html",
    "templates/clearance/approver_dashboard.html",
    "templates/clearance/service_dept_dashboard.html",
    "templates/admin_oversight/deputy_principal_dashboard.html",
    "templates/admin_oversight/quality_assurance_dashboard.html",
    "templates/admin_oversight/registrar_dashboard.html",
]

FOOTER_INCLUDE = """
<!-- Pride in Technology Footer -->
{% include 'partials/pride_footer.html' %}

{% endblock %}"""

def add_footer_to_file(filepath):
    """Add footer to a single dashboard file."""
    if not os.path.exists(filepath):
        print(f"⚠️  File not found: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if footer already exists
    if "pride_footer.html" in content:
        print(f"✓  Footer already exists: {filepath}")
        return True
    
    # Find the last {% endblock %} and add footer before it
    # Pattern: match the last {% endblock %} possibly with extra text after
    pattern = r'({% endblock %})\s*(?:.*?)$'
    
    # Check if file has endblock
    if '{% endblock %}' not in content:
        print(f"⚠️  No endblock found: {filepath}")
        return False
    
    # Replace the last occurrence of {% endblock %}
    parts = content.rsplit('{% endblock %}', 1)
    if len(parts) == 2:
        new_content = parts[0] + FOOTER_INCLUDE
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✅ Updated: {filepath}")
        return True
    else:
        print(f"⚠️  Could not update: {filepath}")
        return False

def main():
    """Main function to update all dashboard files."""
    print("=" * 60)
    print("Adding Pride in Technology Footer to All Dashboards")
    print("=" * 60)
    print()
    
    base_dir = Path(__file__).parent
    updated = 0
    skipped = 0
    failed = 0
    
    for filepath in DASHBOARD_FILES:
        full_path = base_dir / filepath
        result = add_footer_to_file(full_path)
        
        if result is True:
            updated += 1
        elif result is False:
            failed += 1
        else:
            skipped += 1
    
    print()
    print("=" * 60)
    print(f"Summary:")
    print(f"  ✅ Updated: {updated}")
    print(f"  ⏭️  Skipped (already has footer): {skipped}")
    print(f"  ❌ Failed: {failed}")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review the changes")
    print("2. Test dashboards in browser")
    print("3. Commit and push to GitHub")

if __name__ == "__main__":
    main()
