#!/usr/bin/env python3
"""
Test script to simulate a document upload and verify the entire workflow.
"""

import sys
import io
from db import get_service_client

def test_upload_workflow():
    """Test the complete document upload workflow."""
    print("\n" + "="*70)
    print("  TESTING DOCUMENT UPLOAD WORKFLOW")
    print("="*70)
    
    db = get_service_client()
    
    # Get a test student
    print("\n1. Finding test student...")
    students = db.table("user_profiles").select("id, full_name, admission_no").eq("role", "student").limit(1).execute()
    
    if not students.data:
        print("❌ No students found in database")
        return False
    
    student = students.data[0]
    print(f"✅ Using student: {student['full_name']} ({student['admission_no']})")
    
    # Simulate file upload
    print("\n2. Simulating file upload to storage...")
    try:
        storage = db.storage
        
        # Create a test PDF file in memory
        test_file_content = b"%PDF-1.4\nTest PDF content for verification"
        file_path = f"trainee_documents/{student['id']}_passport_photo_test.pdf"
        
        # Try to upload
        result = storage.from_("assessment-evidence").upload(
            file_path,
            test_file_content,
            {"content-type": "application/pdf"}
        )
        
        print(f"✅ File uploaded to storage: {file_path}")
        
        # Get public URL
        public_url = storage.from_("assessment-evidence").get_public_url(file_path)
        print(f"✅ Public URL generated: {public_url[:60]}...")
        
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg.lower():
            print(f"⚠️  File already exists (this is OK): {file_path}")
            public_url = storage.from_("assessment-evidence").get_public_url(file_path)
        else:
            print(f"❌ Upload failed: {e}")
            return False
    
    # Insert into database
    print("\n3. Inserting document record into database...")
    try:
        doc_data = {
            "student_id": student['id'],
            "document_type": "passport_photo",
            "document_name": "Passport Photo",
            "file_url": public_url,
            "file_path": file_path,
            "file_name": "test_passport.pdf",
            "file_size": len(test_file_content),
            "status": "pending"
        }
        
        # Check if document already exists
        existing = db.table("student_personal_documents").select("id").eq("student_id", student['id']).eq("document_type", "passport_photo").execute()
        
        if existing.data:
            # Update existing
            result = db.table("student_personal_documents").update(doc_data).eq("id", existing.data[0]['id']).execute()
            print(f"✅ Updated existing document record: {existing.data[0]['id']}")
        else:
            # Insert new
            result = db.table("student_personal_documents").insert(doc_data).execute()
            print(f"✅ Inserted new document record: {result.data[0]['id']}")
        
    except Exception as e:
        print(f"❌ Database insert failed: {e}")
        return False
    
    # Verify retrieval
    print("\n4. Verifying document can be retrieved...")
    try:
        docs = db.table("student_personal_documents").select("*").eq("student_id", student['id']).execute()
        
        if docs.data:
            print(f"✅ Found {len(docs.data)} document(s) for student")
            
            for doc in docs.data:
                print(f"\n   Document Details:")
                print(f"   - Type: {doc['document_type']}")
                print(f"   - Name: {doc['document_name']}")
                print(f"   - File: {doc['file_name']}")
                print(f"   - Size: {doc['file_size']} bytes")
                print(f"   - Status: {doc['status']}")
                print(f"   - Uploaded: {doc['created_at']}")
        else:
            print("❌ Could not retrieve documents")
            return False
            
    except Exception as e:
        print(f"❌ Retrieval failed: {e}")
        return False
    
    # Clean up test file
    print("\n5. Cleaning up test data...")
    try:
        # Delete from database
        db.table("student_personal_documents").delete().eq("student_id", student['id']).eq("document_type", "passport_photo").execute()
        print("✅ Deleted test document from database")
        
        # Delete from storage
        storage.from_("assessment-evidence").remove([file_path])
        print("✅ Deleted test file from storage")
        
    except Exception as e:
        print(f"⚠️  Cleanup: {e}")
    
    print("\n" + "="*70)
    print("  ✅ WORKFLOW TEST COMPLETED SUCCESSFULLY!")
    print("="*70)
    print("\nThe 'My Documents' feature is working correctly.")
    print("Students can now upload documents through the web interface.")
    print("\n")
    
    return True

if __name__ == "__main__":
    try:
        success = test_upload_workflow()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
