import os

class Config:
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB = os.getenv('MONGO_DB', 'codetracker')
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')  # Optional: for private repos
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {'.c', '.cpp', '.cc', '.cxx'}
    COMPILE_TIMEOUT = 30  # seconds