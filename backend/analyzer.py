import subprocess
import os
import tempfile
from config import Config
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

class CodeAnalyzer:
    def __init__(self):
        self.compile_timeout = Config.COMPILE_TIMEOUT
        
    def find_c_cpp_files(self, repo_path):
        """Find all C and C++ files in repository"""
        c_files = []
        cpp_files = []
        
        for root, dirs, files in os.walk(repo_path):
            # Skip hidden directories and common build directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'dist', 'node_modules']]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                if file.endswith('.c'):
                    c_files.append((file_path, rel_path, 'c'))
                elif any(file.endswith(ext) for ext in ['.cpp', '.cc', '.cxx']):
                    cpp_files.append((file_path, rel_path, 'cpp'))
        
        return c_files + cpp_files

    def analyze_file(self, file_path, language):
        """Analyze a single C/C++ file"""
        result = {
            'errors': [],
            'warnings': [],
            'compile_output': '',
            'passed': True
        }
        
        try:
            # Create temp file for output
            with tempfile.NamedTemporaryFile(suffix='.out', delete=False) as tmp:
                output_file = tmp.name
            
            # Compile command based on language
            if language == 'c':
                cmd = ['gcc', '-fsyntax-only', '-Wall', '-Wextra', '-std=c11', file_path]
            else:  # cpp
                cmd = ['g++', '-fsyntax-only', '-Wall', '-Wextra', '-std=c++14', file_path]
            
            # Run compilation
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.compile_timeout
            )
            
            # Parse output
            stderr_lines = process.stderr.split('\n')
            
            for line in stderr_lines:
                if not line.strip():
                    continue
                    
                # Parse GCC/Clang error format
                # filename:line:column: error/warning: message
                parts = line.split(':', 3)
                if len(parts) >= 4:
                    try:
                        line_num = int(parts[1])
                        msg_type = parts[2].strip()
                        message = parts[3].strip()
                        
                        if 'error' in msg_type.lower():
                            result['errors'].append({
                                'line': line_num,
                                'message': message,
                                'type': 'error'
                            })
                            result['passed'] = False
                        elif 'warning' in msg_type.lower():
                            result['warnings'].append({
                                'line': line_num,
                                'message': message,
                                'type': 'warning'
                            })
                    except (ValueError, IndexError):
                        # Line number parsing failed, include as general error
                        if 'error' in line.lower():
                            result['errors'].append({
                                'line': 0,
                                'message': line,
                                'type': 'error'
                            })
                            result['passed'] = False
                        elif 'warning' in line.lower():
                            result['warnings'].append({
                                'line': 0,
                                'message': line,
                                'type': 'warning'
                            })
            
            result['compile_output'] = process.stderr
            
            # Clean up
            if os.path.exists(output_file):
                os.unlink(output_file)
                
        except subprocess.TimeoutExpired:
            result['errors'].append({
                'line': 0,
                'message': f'Compilation timeout after {self.compile_timeout} seconds',
                'type': 'error'
            })
            result['passed'] = False
        except Exception as e:
            result['errors'].append({
                'line': 0,
                'message': f'Analysis error: {str(e)}',
                'type': 'error'
            })
            result['passed'] = False
        
        return result

    def analyze_repository(self, repo_path, submission_id, db, max_workers=4):
        """Analyze all C/C++ files in repository"""
        files = self.find_c_cpp_files(repo_path)
        
        if not files:
            return {'total_files': 0, 'analyzed_files': 0}
        
        # Update submission with total files
        db.submissions.update_one(
            {'_id': submission_id},
            {'$set': {'total_files': len(files), 'status': 'analyzing'}}
        )
        
        results = []
        total_errors = 0
        total_warnings = 0
        
        # Analyze files in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(self.analyze_file, file_path, language): (file_path, rel_path, language)
                for file_path, rel_path, language in files
            }
            
            analyzed_count = 0
            for future in as_completed(future_to_file):
                file_path, rel_path, language = future_to_file[future]
                
                try:
                    analysis_result = future.result()
                    
                    # Store in database
                    result_doc = {
                        'submission_id': submission_id,
                        'file_path': rel_path,
                        'file_name': os.path.basename(file_path),
                        'language': language,
                        'status': 'analyzed',
                        'errors': analysis_result['errors'],
                        'warnings': analysis_result['warnings'],
                        'compile_output': analysis_result['compile_output'],
                        'analyzed_at': datetime.utcnow(),
                        'passed': analysis_result['passed']
                    }
                    
                    db.analysis_results.insert_one(result_doc)
                    
                    total_errors += len(analysis_result['errors'])
                    total_warnings += len(analysis_result['warnings'])
                    
                    analyzed_count += 1
                    
                    # Update submission progress
                    db.submissions.update_one(
                        {'_id': submission_id},
                        {
                            '$set': {
                                'analyzed_files': analyzed_count,
                                'errors_count': total_errors,
                                'warnings_count': total_warnings
                            }
                        }
                    )
                    
                except Exception as e:
                    print(f"Error analyzing {rel_path}: {e}")
        
        # Mark submission as completed
        db.submissions.update_one(
            {'_id': submission_id},
            {
                '$set': {
                    'status': 'completed',
                    'completed_at': datetime.utcnow()
                }
            }
        )
        
        return {
            'total_files': len(files),
            'analyzed_files': analyzed_count,
            'total_errors': total_errors,
            'total_warnings': total_warnings
        }