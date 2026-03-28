# setup_firebase.py
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

def setup_database():
    """Setup Firebase database with initial data"""
    
    print("=" * 60)
    print("🚀 CodeTracker Firebase Setup")
    print("=" * 60)
    
    # Connect to Firebase
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Connected to Firebase")
    except Exception as e:
        print(f"❌ Firebase connection failed: {e}")
        return
    
    # Create assignments
    print("\n📚 Setting up assignments...")
    
    assignments = [
        {
            "assignment_id": "c_language_basics",
            "title": "C Language Basics",
            "description": "Basic C programming exercises including loops, functions, and arrays",
            "due_date": "March 10, 2026",
            "difficulty": "Medium",
            "language": "C",
            "repo_url": "https://github.com/CharlieGadingan/clanguage.git",
            "branch": "main",
            "created_at": firestore.SERVER_TIMESTAMP
        },
        {
            "assignment_id": "cpp_programming",
            "title": "C++ Programming Fundamentals",
            "description": "Object-oriented programming with C++ including classes and inheritance",
            "due_date": "March 24, 2026",
            "difficulty": "Hard",
            "language": "C++",
            "repo_url": "https://github.com/CharlieGadingan/cpp.git",
            "branch": "main",
            "created_at": firestore.SERVER_TIMESTAMP
        }
    ]
    
    for assignment in assignments:
        assignment_id = assignment.pop("assignment_id")
        db.collection('assignments').document(assignment_id).set(assignment, merge=True)
        print(f"   ✅ Created/Updated: {assignment['title']}")
    
    # Create student
    print("\n👤 Setting up student profile...")
    
    student_data = {
        "student_id": "student123",
        "name": "Dexter Facelo",
        "email": "dexter.facelo@student.edu",
        "year": 3,
        "course": "Computer Science",
        "created_at": firestore.SERVER_TIMESTAMP
    }
    
    db.collection('students').document("student123").set(student_data, merge=True)
    print("   ✅ Created/Updated student")
    
    # FIXED: Get counts properly - convert generator to list
    print("\n📊 Final database stats:")
    
    # Count assignments (convert generator to list first)
    assignments_list = list(db.collection('assignments').stream())
    print(f"   Assignments: {len(assignments_list)}")
    
    # Count students
    students_list = list(db.collection('students').stream())
    print(f"   Students: {len(students_list)}")
    
    # List all assignments
    print("\n📋 Assignments in database:")
    for doc in assignments_list:
        data = doc.to_dict()
        created = data.get('created_at', 'unknown')
        if hasattr(created, 'strftime'):
            created = created.strftime('%Y-%m-%d')
        print(f"   • {data['title']} (ID: {doc.id})")
        print(f"     Repo: {data['repo_url']}")
        print()
    
    print("=" * 60)
    print("✅ Database setup complete!")
    print("=" * 60)

if __name__ == "__main__":
    setup_database()