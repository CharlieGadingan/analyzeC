# app.py - Firebase Version
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import tempfile
import shutil
import subprocess
import uuid
import threading
import re
from git import Repo
import firebase_admin
from firebase_admin import credentials, firestore, auth
import json

# Initialize Firebase Admin SDK
cred = credentials.Certificate("serviceAccountKey.json")  # Download from Firebase Console
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
CORS(app)

# Collections (Firestore equivalent of MongoDB collections)
assignments_ref = db.collection('assignments')
students_ref = db.collection('students')
submissions_ref = db.collection('submissions')
reviews_ref = db.collection('reviews')
analysis_results_ref = db.collection('analysis_results')

def clean_error_message(error_line):
    """Extract error message - KEEPS ALL ERRORS"""
    import re
    
    # Try to extract the main error with line number
    main_error = re.search(r':(\d+):(\d+):\s+(error|warning):\s+(.*)$', error_line, re.IGNORECASE)
    if main_error:
        line_num = int(main_error.group(1))
        msg_type = main_error.group(3).lower()
        message = main_error.group(4).strip()
        message = re.sub(r'\s*\[.*?\]$', '', message).strip()
        
        return {
            'line': line_num,
            'type': msg_type,
            'message': message
        }
    
    # Try without column number
    simple_error = re.search(r':(\d+):\s+(error|warning):\s+(.*)$', error_line, re.IGNORECASE)
    if simple_error:
        line_num = int(simple_error.group(1))
        msg_type = simple_error.group(2).lower()
        message = simple_error.group(3).strip()
        message = re.sub(r'\s*\[.*?\]$', '', message).strip()
        
        return {
            'line': line_num,
            'type': msg_type,
            'message': message
        }
    
    # Last resort - extract error without line number
    if 'error:' in error_line.lower():
        parts = error_line.lower().split('error:')
        return {
            'line': 0,
            'type': 'error',
            'message': parts[-1].strip()
        }
    elif 'warning:' in error_line.lower():
        parts = error_line.lower().split('warning:')
        return {
            'line': 0,
            'type': 'warning',
            'message': parts[-1].strip()
        }
    
    # For notes and other messages, still include them
    return {
        'line': 0,
        'type': 'info',
        'message': error_line.strip()
    }

def detect_root_cause(errors, file_lines):
    """Analyze errors to find the root cause"""
    if not errors:
        return None
    
    errors.sort(key=lambda x: x['line'])
    
    root_patterns = [
        (r'missing terminating', 'Missing closing quote or character'),
        (r'expected .* before', 'Missing syntax element'),
        (r'unexpected end of file', 'Unclosed block or missing closing brace'),
        (r'stray .* in program', 'Invalid character in code'),
        (r'unknown type name', 'Type not defined or missing include'),
        (r'undeclared identifier', 'Variable not declared'),
        (r'missing sentinel', 'Missing NULL terminator'),
        (r'expected declaration', 'Missing function or variable declaration'),
        (r'expected expression', 'Incomplete expression'),
        (r'expected identifier', 'Missing name or identifier'),
        (r'expected \',\',?.*;', 'Missing semicolon'),
        (r'expected \'}\'', 'Missing closing brace'),
        (r'expected \'\)\'', 'Missing closing parenthesis'),
        (r'conflicting types', 'Function signature mismatch'),
    ]
    
    root_candidates = []
    for error in errors:
        for pattern, reason in root_patterns:
            if re.search(pattern, error['message'], re.IGNORECASE):
                error['root_reason'] = reason
                root_candidates.append(error)
                break
    
    if root_candidates:
        root_candidates.sort(key=lambda x: x['line'])
        return root_candidates[0]
    
    return errors[0] if errors else None

def suggest_fix(error, file_lines):
    """Suggest a fix based on the error type"""
    message = error['message'].lower()
    line_num = error['line']
    
    context = ""
    if line_num > 0 and line_num <= len(file_lines):
        context = file_lines[line_num - 1].strip()
    
    if 'expected' in message and (';' in message or 'semicolon' in message):
        if context and not context.endswith(';') and not context.endswith('{') and not context.endswith('}'):
            return "Add a semicolon ';' at the end of this line"
        return "Missing semicolon - check the end of the previous statement"
    
    elif 'expected' in message and '}' in message:
        return "Add a closing brace '}' - check for unclosed blocks"
    
    elif 'expected' in message and ')' in message:
        open_paren = context.count('(')
        close_paren = context.count(')')
        if open_paren > close_paren:
            return f"Add {open_paren - close_paren} closing parenthesis ')'"
        return "Missing closing parenthesis ')'"
    
    elif 'unterminated' in message and 'comment' in message:
        return "Close the multi-line comment with '*/'"
    
    elif 'unknown type name' in message:
        match = re.search(r'unknown type name [\'"]?(\w+)[\'"]?', message, re.IGNORECASE)
        if match:
            return f"Type '{match.group(1)}' is not defined. Did you forget to include a header (like #include <stdio.h>) or declare it?"
    
    elif 'undeclared identifier' in message:
        match = re.search(r'undeclared identifier [\'"]?(\w+)[\'"]?', message, re.IGNORECASE)
        if match:
            return f"Variable '{match.group(1)}' is not declared. Declare it before use (e.g., 'int {match.group(1)};')"
    
    return "Check the syntax around this line"

def analyze_file(file_path, language, file_content):
    """Analyze a single file - SHOWS ALL ERRORS"""
    errors = []
    warnings = []
    file_lines = file_content.split('\n') if file_content else []
    
    try:
        if language == 'c':
            cmd = ['gcc', '-fsyntax-only', '-Wall', '-Wextra', '-std=c11', file_path]
        elif language == 'cpp':
            cmd = ['g++', '-fsyntax-only', '-Wall', '-Wextra', '-std=c++14', file_path]
        else:
            return errors, warnings
        
        # Run compilation
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Parse ALL errors and warnings from stderr
        seen_messages = set()
        
        for line in process.stderr.split('\n'):
            if not line.strip():
                continue
            
            cleaned = clean_error_message(line)
            if cleaned is None:
                continue
            
            # Create unique key for this message
            msg_key = f"{cleaned['line']}:{cleaned['type']}:{cleaned['message']}"
            if msg_key in seen_messages:
                continue
            
            seen_messages.add(msg_key)
            
            if cleaned['type'] == 'error':
                errors.append({
                    'line': cleaned['line'],
                    'message': cleaned['message'],
                    'type': 'error'
                })
            elif cleaned['type'] == 'warning':
                warnings.append({
                    'line': cleaned['line'],
                    'message': cleaned['message'],
                    'type': 'warning'
                })
        
        # Sort by line number
        errors.sort(key=lambda x: x['line'])
        warnings.sort(key=lambda x: x['line'])
        
    except subprocess.TimeoutExpired:
        errors.append({'line': 0, 'message': 'Compilation timeout - file may be too complex', 'type': 'error'})
    except FileNotFoundError:
        errors.append({'line': 0, 'message': f'Compiler not found. Please install {"gcc" if language=="c" else "g++"}.', 'type': 'error'})
    except Exception as e:
        errors.append({'line': 0, 'message': f'Analysis error: {str(e)}', 'type': 'error'})
    
    return errors, warnings

@app.route('/api/assignments/<student_id>', methods=['GET'])
def get_student_assignments(student_id):
    """Get all assignments for a student"""
    try:
        # Check if student exists
        student_doc = students_ref.document(student_id).get()
        if not student_doc.exists:
            student_data = {
                "student_id": student_id,
                "name": "Dexter Facelo",
                "email": "dexter.facelo@student.edu",
                "year": 3,
                "course": "Computer Science",
                "created_at": firestore.SERVER_TIMESTAMP
            }
            students_ref.document(student_id).set(student_data)
        
        # Get all assignments
        assignments = []
        assignments_snapshot = assignments_ref.stream()
        
        for doc in assignments_snapshot:
            assignment = doc.to_dict()
            assignment['assignment_id'] = doc.id
            
            # Get submission for this assignment
            submission_doc = submissions_ref.document(f"{student_id}_{assignment['assignment_id']}").get()
            
            assignment_data = {
                "assignment_id": assignment["assignment_id"],
                "title": assignment["title"],
                "description": assignment.get("description", ""),
                "due_date": assignment["due_date"],
                "difficulty": assignment["difficulty"],
                "language": assignment["language"],
                "repo_url": assignment["repo_url"],
                "branch": assignment.get("branch", "main"),
                "status": "pending",
                "grade": None,
                "submission_id": None
            }
            
            if submission_doc.exists:
                submission = submission_doc.to_dict()
                assignment_data["status"] = submission.get("status", "pending")
                assignment_data["submission_id"] = f"{student_id}_{assignment['assignment_id']}"
                
                # Get review
                review_doc = reviews_ref.document(assignment_data["submission_id"]).get()
                if review_doc.exists:
                    review = review_doc.to_dict()
                    assignment_data["grade"] = review.get("grade")
                
                # Get analysis results
                analysis_results = []
                analysis_snapshot = analysis_results_ref.where("submission_id", "==", assignment_data["submission_id"]).stream()
                
                total_errors = 0
                total_warnings = 0
                file_count = 0
                for doc in analysis_snapshot:
                    file_count += 1
                    result = doc.to_dict()
                    total_errors += len([e for e in result.get("errors", []) if e.get('type') == 'error'])
                    total_warnings += len(result.get("warnings", []))
                
                assignment_data["errors_count"] = total_errors
                assignment_data["warnings_count"] = total_warnings
                assignment_data["total_files"] = file_count
            
            assignments.append(assignment_data)
        
        return jsonify({"success": True, "assignments": assignments})
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        return jsonify({
            'status': 'healthy',
            'database': 'firebase',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/api/submit-repo', methods=['POST'])
def submit_repository():
    """Submit a repository for analysis"""
    try:
        data = request.json
        
        student_id = data.get('student_id', 'student123')
        assignment_id = data.get('assignment_id')
        repo_url = data.get('repo_url')
        branch = data.get('branch', 'main')
        
        if not all([assignment_id, repo_url]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        submission_id = f"{student_id}_{assignment_id}"
        
        # Check if submission exists
        submission_doc = submissions_ref.document(submission_id).get()
        
        if submission_doc.exists:
            print(f"📝 Using existing submission: {submission_id}")
            # Delete old analysis results
            analysis_snapshot = analysis_results_ref.where("submission_id", "==", submission_id).stream()
            for doc in analysis_snapshot:
                doc.reference.delete()
            
            # Reset submission
            submissions_ref.document(submission_id).set({
                'status': 'pending',
                'completed_at': None,
                'total_files': 0,
                'analyzed_files': 0,
                'errors_count': 0,
                'warnings_count': 0,
                'updated_at': firestore.SERVER_TIMESTAMP
            }, merge=True)
        else:
            # Create new submission
            submission_data = {
                'student_id': student_id,
                'assignment_id': assignment_id,
                'repo_url': repo_url,
                'branch': branch,
                'status': 'pending',
                'created_at': firestore.SERVER_TIMESTAMP,
                'completed_at': None,
                'total_files': 0,
                'analyzed_files': 0,
                'errors_count': 0,
                'warnings_count': 0
            }
            submissions_ref.document(submission_id).set(submission_data)
            print(f"📝 Created new submission: {submission_id}")
        
        # Start analysis in background
        thread = threading.Thread(
            target=analyze_repository_background,
            args=(submission_id, repo_url, branch)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'submission_id': submission_id,
            'status': 'pending'
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/save-grade', methods=['POST'])
def save_grade():
    """Save grade for a submission"""
    try:
        data = request.json
        submission_id = data.get('submission_id')
        grade = data.get('grade')
        
        if not submission_id:
            return jsonify({'success': False, 'error': 'Submission ID required'}), 400
        
        if grade is None or not isinstance(grade, (int, float)) or grade < 0 or grade > 100:
            return jsonify({'success': False, 'error': 'Grade must be a number between 0 and 100'}), 400
        
        # Check if submission exists
        submission_doc = submissions_ref.document(submission_id).get()
        if not submission_doc.exists:
            return jsonify({'success': False, 'error': 'Submission not found'}), 404
        
        # Save grade in review
        review_data = {
            'grade': grade,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        reviews_ref.document(submission_id).set(review_data, merge=True)
        print(f"✅ Saved grade for submission {submission_id}: {grade}")
        
        return jsonify({
            'success': True,
            'message': f'Grade {grade} saved successfully'
        })
        
    except Exception as e:
        print(f"❌ Error saving grade: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analysis/<submission_id>', methods=['GET'])
def get_analysis(submission_id):
    """Get analysis results for a submission"""
    try:
        submission_doc = submissions_ref.document(submission_id).get()
        if not submission_doc.exists:
            return jsonify({'success': False, 'error': 'Submission not found'}), 404
        
        submission = submission_doc.to_dict()
        submission['_id'] = submission_id
        
        # Get all analysis results
        results = []
        analysis_snapshot = analysis_results_ref.where("submission_id", "==", submission_id).stream()
        for doc in analysis_snapshot:
            result = doc.to_dict()
            result['_id'] = doc.id
            results.append(result)
        
        # Get review if exists
        review_doc = reviews_ref.document(submission_id).get()
        review = review_doc.to_dict() if review_doc.exists else None
        
        return jsonify({
            'success': True,
            'submission': submission,
            'files': results,
            'review': review
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/<submission_id>', methods=['GET'])
def get_files(submission_id):
    """Get list of ALL analyzed files with content"""
    try:
        files = []
        analysis_snapshot = analysis_results_ref.where("submission_id", "==", submission_id).stream()
        
        for doc in analysis_snapshot:
            file_data = doc.to_dict()
            file_data['_id'] = doc.id
            files.append(file_data)
        
        files.sort(key=lambda x: x.get('file_path', ''))
        
        print(f"📤 Returning {len(files)} files for submission {submission_id}")
        
        return jsonify({
            'success': True,
            'files': files
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/save-feedback', methods=['POST'])
def save_feedback():
    """Save feedback for a submission"""
    try:
        data = request.json
        
        submission_id = data.get('submission_id')
        reviewer_id = data.get('reviewer_id', 'instructor1')
        feedback = data.get('feedback', '')
        
        if not submission_id:
            return jsonify({'success': False, 'error': 'Submission ID required'}), 400
        
        # Check if submission exists
        submission_doc = submissions_ref.document(submission_id).get()
        if not submission_doc.exists:
            return jsonify({'success': False, 'error': 'Submission not found'}), 404
        
        # Save feedback in review
        review_data = {
            'feedback': feedback,
            'reviewer_id': reviewer_id,
            'status': 'completed',
            'completed_at': firestore.SERVER_TIMESTAMP
        }
        
        reviews_ref.document(submission_id).set(review_data, merge=True)
        print(f"✅ Saved feedback for submission {submission_id}")
        
        # Update submission status
        submissions_ref.document(submission_id).update({
            'status': 'reviewed',
            'reviewed_at': firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({
            'success': True,
            'message': 'Feedback saved successfully'
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def analyze_repository_background(submission_id, repo_url, branch):
    """Background task for repository analysis"""
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        print(f"📦 Cloning from {repo_url} to {temp_dir}")
        
        repo = Repo.clone_from(repo_url, temp_dir, branch=branch, depth=1)
        
        latest_commit = repo.head.commit
        print(f"   📍 Latest commit: {latest_commit.hexsha[:8]} - {latest_commit.message.strip()}")
        
        # Find ALL files
        all_files = []
        
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '.git' and d != '__pycache__']
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, temp_dir)
                
                file_stat = os.stat(file_path)
                mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                
                language = 'unknown'
                ext = os.path.splitext(file)[1].lower()
                
                if ext in ['.c']:
                    language = 'c'
                elif ext in ['.cpp', '.cc', '.cxx']:
                    language = 'cpp'
                elif ext in ['.h', '.hpp']:
                    language = 'header'
                elif ext in ['.py']:
                    language = 'python'
                elif ext in ['.js']:
                    language = 'javascript'
                elif ext in ['.html', '.htm']:
                    language = 'html'
                elif ext in ['.css']:
                    language = 'css'
                elif ext in ['.md']:
                    language = 'markdown'
                elif ext in ['.txt']:
                    language = 'text'
                elif ext in ['.json']:
                    language = 'json'
                
                all_files.append((file_path, rel_path, language, file, mod_time))
        
        print(f"🔍 Found {len(all_files)} total files")
        
        # Update submission
        submissions_ref.document(submission_id).update({
            'total_files': len(all_files),
            'status': 'analyzing',
            'last_commit': latest_commit.hexsha,
            'last_commit_message': latest_commit.message.strip(),
            'last_commit_date': datetime.fromtimestamp(latest_commit.committed_date)
        })
        
        total_errors = 0
        total_warnings = 0
        processed_count = 0
        
        for file_path, rel_path, language, file_name, mod_time in all_files:
            try:
                # Read file content
                content = ""
                file_size = os.path.getsize(file_path)
                
                try:
                    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'ascii']
                    for encoding in encodings:
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                content = f.read()
                            break
                        except (UnicodeDecodeError, LookupError):
                            continue
                    else:
                        with open(file_path, 'rb') as f:
                            content = f.read().decode('utf-8', errors='ignore')
                except Exception as e:
                    content = f"// Error reading file: {str(e)}"
                
                # Analyze file
                errors, warnings = analyze_file(file_path, language, content)
                
                # Store in Firebase
                doc_id = f"{submission_id}_{rel_path.replace('/', '_')}"
                result_data = {
                    'submission_id': submission_id,
                    'file_path': rel_path.replace('\\', '/'),
                    'file_name': file_name,
                    'language': language,
                    'status': 'analyzed',
                    'errors': errors,
                    'warnings': warnings,
                    'content': content,
                    'analyzed_at': firestore.SERVER_TIMESTAMP,
                    'passed': len(errors) == 0,
                    'file_size': file_size,
                    'file_modified': mod_time
                }
                
                analysis_results_ref.document(doc_id).set(result_data)
                
                total_errors += len([e for e in errors if e.get('type') == 'error'])
                total_warnings += len(warnings)
                processed_count += 1
                
                if processed_count % 5 == 0:
                    submissions_ref.document(submission_id).update({
                        'analyzed_files': processed_count,
                        'errors_count': total_errors,
                        'warnings_count': total_warnings
                    })
                    print(f"📊 Progress: {processed_count}/{len(all_files)} files")
                
                if errors:
                    status_icon = "❌"
                elif warnings:
                    status_icon = "⚠️"
                else:
                    status_icon = "✅"
                    
                print(f"{status_icon} {rel_path}")
                
            except Exception as e:
                print(f"❌ Error processing {rel_path}: {e}")
                doc_id = f"{submission_id}_{rel_path.replace('/', '_')}"
                result_data = {
                    'submission_id': submission_id,
                    'file_path': rel_path.replace('\\', '/'),
                    'file_name': file_name,
                    'language': language,
                    'status': 'failed',
                    'errors': [{'line': 0, 'message': f'Processing error: {str(e)}', 'type': 'error'}],
                    'warnings': [],
                    'content': f"// Error processing file: {str(e)}",
                    'analyzed_at': firestore.SERVER_TIMESTAMP,
                    'passed': False,
                    'file_size': 0
                }
                analysis_results_ref.document(doc_id).set(result_data)
                total_errors += 1
                processed_count += 1
        
        # Final update
        submissions_ref.document(submission_id).update({
            'status': 'completed',
            'completed_at': firestore.SERVER_TIMESTAMP,
            'analyzed_files': processed_count,
            'errors_count': total_errors,
            'warnings_count': total_warnings
        })
        
        print(f"\n✅ Analysis complete for {submission_id}")
        print(f"   Total files: {len(all_files)}")
        print(f"   Total errors: {total_errors}")
        print(f"   Total warnings: {total_warnings}")
        
    except Exception as e:
        print(f"❌ Background analysis failed: {e}")
        submissions_ref.document(submission_id).update({
            'status': 'failed',
            'error': str(e)
        })
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"🧹 Cleaned up temporary directory")

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'name': 'CodeTracker API',
        'version': '1.0.0',
        'status': 'running',
        'database': 'firebase',
        'endpoints': [
            '/api/health',
            '/api/assignments/<student_id>',
            '/api/submit-repo',
            '/api/analysis/<submission_id>',
            '/api/files/<submission_id>',
            '/api/save-grade',
            '/api/save-feedback'
        ]
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 CodeTracker Backend Server (Firebase)")
    print("=" * 60)
    print(f"📡 Database: Firebase Firestore")
    print(f"🌐 Server running on: http://localhost:5500")
    print("=" * 60)
    
    app.run(debug=True, port=5500, host='0.0.0.0')