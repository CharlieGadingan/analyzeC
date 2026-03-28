import os
import tempfile
import shutil
import zipfile
import io
import requests
from git import Repo
from config import Config
import threading
import time

class GitHubUtils:
    @staticmethod
    def download_repository(repo_url, branch='main'):
        """Download repository and return path to temp directory"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Clone the repository
            if Config.GITHUB_TOKEN:
                # For private repos
                auth_url = repo_url.replace('https://', f'https://{Config.GITHUB_TOKEN}@')
                Repo.clone_from(auth_url, temp_dir, branch=branch, depth=1)
            else:
                # For public repos
                Repo.clone_from(repo_url, temp_dir, branch=branch, depth=1)
            
            return temp_dir
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise Exception(f"Failed to clone repository: {str(e)}")

    @staticmethod
    def download_repository_zip(repo_url, branch='main'):
        """Alternative: Download as ZIP (faster for large repos)"""
        # Convert GitHub URL to archive URL
        # https://github.com/user/repo -> https://api.github.com/repos/user/repo/zipball/branch
        
        parts = repo_url.rstrip('/').split('/')
        if len(parts) < 5:
            raise Exception("Invalid GitHub URL")
        
        user = parts[-2]
        repo = parts[-1]
        
        zip_url = f"https://api.github.com/repos/{user}/{repo}/zipball/{branch}"
        
        headers = {}
        if Config.GITHUB_TOKEN:
            headers['Authorization'] = f'token {Config.GITHUB_TOKEN}'
        
        response = requests.get(zip_url, headers=headers, stream=True)
        if response.status_code != 200:
            raise Exception(f"Failed to download: {response.status_code}")
        
        temp_dir = tempfile.mkdtemp()
        zip_data = io.BytesIO(response.content)
        
        with zipfile.ZipFile(zip_data) as zip_ref:
            zip_ref.extractall(temp_dir)
            
            # Move files from subdirectory to root
            extracted_items = os.listdir(temp_dir)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_items[0])):
                subdir = os.path.join(temp_dir, extracted_items[0])
                for item in os.listdir(subdir):
                    shutil.move(os.path.join(subdir, item), temp_dir)
                os.rmdir(subdir)
        
        return temp_dir

    @staticmethod
    def cleanup_temp_dir(temp_dir):
        """Remove temporary directory"""
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)