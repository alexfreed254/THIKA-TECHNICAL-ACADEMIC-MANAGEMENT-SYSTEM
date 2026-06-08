#!/usr/bin/env python3
"""
Quick verification script to check if My Documents feature is properly set up.
This checks:
1. Database connection
2. Table exists
3. Storage bucket exists
4. Basic read/write permissions
"""

import sys
from db import get_service_client

def print_header(text):
    """Print a formatted header."""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def print_status(check_name, passed, message=""):
    """Print check status."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {check_name}")
    if message:
        print(f"     {message}")

def main():
    print_header("MY DOCUMENTS FEATURE VERIFICATION")
    print("This script checks if the My Documents feature is ready to use.")
    
    all_passed = True
    
    # ── CHECK 1: Database Connection ──────────────────────────────────────
    print_header("1. Database Connection")
    try:
        db = get_service_client()
        print_status("Database connection", True, "Successfully connected to Supabase")
    except Exception as e:
        print_status("Database connection", False, f"Error: {e}")
        print("\n❌ Cannot proceed without database connection. Check .env file.")
        sys.exit(1)
    
    # ── CHECK 2: Table Exists ─────────────────────────────────────────────
    print_header("2. Table: student_personal_documents")
    try:
        # Try to query the table
        result = db.table("student_personal_documents").select("id").limit(1).execute()
        print_status("Table exists", True, "Table is accessible")
        print(f"     Current documents in table: {len(result.data) if result.data else 0}")
    except Exception as e:
        error_msg = str(e)
        if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
            print_status("Table exists", False, "Table NOT FOUND - Migration required!")
            print("\n     💡 SOLUTION: Run migration_student_documents.sql")
            print("     1. Open Supabase Dashboard → SQL Editor")
            print("     2. Copy contents of migration_student_documents.sql")
            print("     3. Paste and run the SQL script")
            all_passed = False
        else:
            print_status("Table exists", False, f"Error: {error_msg}")
            all_passed = False
    
    # ── CHECK 3: Storage Bucket ───────────────────────────────────────────
    print_header("3. Storage Bucket: assessment-evidence")
    try:
        storage = db.storage
        buckets = storage.list_buckets()
        bucket_names = [b['name'] for b in buckets] if buckets else []
        
        if 'assessment-evidence' in bucket_names:
            print_status("Storage bucket exists", True, "Bucket 'assessment-evidence' found")
        else:
            print_status("Storage bucket exists", False, "Bucket NOT FOUND")
            print("\n     💡 SOLUTION: Create bucket in Supabase Dashboard")
            print("     1. Go to Storage section")
            print("     2. Create new bucket: 'assessment-evidence'")
            print("     3. Set as public: Yes")
            all_passed = False
            
        print(f"     Available buckets: {', '.join(bucket_names) if bucket_names else 'None'}")
    except Exception as e:
        print_status("Storage bucket check", False, f"Error: {e}")
        print("     Note: Storage check may fail if permissions are restricted")
    
    # ── CHECK 4: Test Write Permission (if table exists) ──────────────────
    if all_passed:
        print_header("4. Test Data Operations")
        try:
            # Get a test student (first student in database)
            students = db.table("user_profiles").select("id, full_name").eq("role", "student").limit(1).execute()
            
            if not students.data:
                print_status("Test data operations", False, "No students in database to test with")
            else:
                student_id = students.data[0]['id']
                student_name = students.data[0]['full_name']
                print(f"     Testing with student: {student_name}")
                
                # Try to insert a test document
                test_doc = {
                    "student_id": student_id,
                    "document_type": "_verification_test_doc",
                    "document_name": "Verification Test",
                    "file_url": "https://example.com/test.pdf",
                    "file_path": "test/verification.pdf",
                    "file_name": "verification.pdf",
                    "file_size": 1024,
                    "status": "pending"
                }
                
                insert_result = db.table("student_personal_documents").insert(test_doc).execute()
                
                if insert_result.data:
                    doc_id = insert_result.data[0]['id']
                    print_status("INSERT test", True, f"Document ID: {doc_id}")
                    
                    # Try to read it back
                    read_result = db.table("student_personal_documents").select("*").eq("id", doc_id).execute()
                    if read_result.data:
                        print_status("SELECT test", True, "Successfully read document")
                    else:
                        print_status("SELECT test", False, "Could not read back document")
                        all_passed = False
                    
                    # Try to update it
                    update_result = db.table("student_personal_documents").update({"status": "approved"}).eq("id", doc_id).execute()
                    if update_result.data:
                        print_status("UPDATE test", True, "Successfully updated document")
                    else:
                        print_status("UPDATE test", False, "Could not update document")
                        all_passed = False
                    
                    # Clean up - delete test document
                    db.table("student_personal_documents").delete().eq("id", doc_id).execute()
                    print_status("DELETE test", True, "Successfully deleted test document")
                else:
                    print_status("INSERT test", False, "Could not insert test document")
                    all_passed = False
                    
        except Exception as e:
            print_status("Test data operations", False, f"Error: {e}")
            all_passed = False
    
    # ── CHECK 5: Count Existing Documents ─────────────────────────────────
    if all_passed:
        print_header("5. Current Document Statistics")
        try:
            all_docs = db.table("student_personal_documents").select("document_type, status").execute()
            
            if all_docs.data:
                total = len(all_docs.data)
                pending = sum(1 for d in all_docs.data if d.get('status') == 'pending')
                approved = sum(1 for d in all_docs.data if d.get('status') == 'approved')
                rejected = sum(1 for d in all_docs.data if d.get('status') == 'rejected')
                
                print(f"     Total documents: {total}")
                print(f"     Pending: {pending}")
                print(f"     Approved: {approved}")
                print(f"     Rejected: {rejected}")
                
                # Count by type
                types = {}
                for doc in all_docs.data:
                    doc_type = doc.get('document_type', 'unknown')
                    types[doc_type] = types.get(doc_type, 0) + 1
                
                print("\n     Documents by type:")
                for doc_type, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
                    print(f"       - {doc_type}: {count}")
            else:
                print("     No documents uploaded yet")
                
        except Exception as e:
            print(f"     Could not fetch statistics: {e}")
    
    # ── FINAL SUMMARY ─────────────────────────────────────────────────────
    print_header("VERIFICATION SUMMARY")
    
    if all_passed:
        print("\n✅ ALL CHECKS PASSED!")
        print("\nThe 'My Documents' feature is ready to use.")
        print("\nNext steps:")
        print("  1. Login as a student")
        print("  2. Navigate to 'My Documents' menu")
        print("  3. Upload documents (passport photo, admission letter, etc.)")
        print("  4. Verify documents appear in the list")
    else:
        print("\n❌ SOME CHECKS FAILED")
        print("\nThe 'My Documents' feature needs setup before use.")
        print("\nMost likely issue: Database migration not run yet")
        print("\n🔧 QUICK FIX:")
        print("  1. Open: migration_student_documents.sql")
        print("  2. Copy the entire SQL script")
        print("  3. Go to Supabase Dashboard → SQL Editor")
        print("  4. Paste and run the script")
        print("  5. Run this verification script again")
    
    print("\n" + "="*70)
    print()
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nVerification cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
