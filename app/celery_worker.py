from celery import Celery
import time
import os
import requests
import openai
from dotenv import load_dotenv
import logging
from tiktoken import encoding_for_model
import re
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get Redis URL from environment or use default
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
logger.info(f"Using Redis URL: {REDIS_URL}")

# Initialize Celery with Redis backend
celery = Celery('app.celery_worker')

# Configure Celery
celery.config_from_object('app.celeryconfig')

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    raise ValueError("OpenAI API key not found in environment variables")
logger.info("OpenAI API key configured")

def check_repo_visibility(owner: str, repo: str) -> bool:
    """
    Check if a repository is public or private
    Returns True if repo is private, False if public
    """
    try:
        # Try to fetch repo info without authentication
        response = requests.get(f'https://api.github.com/repos/{owner}/{repo}')
        if response.status_code == 404:
            # If repo not found, it might be private or not exist
            return True
        repo_data = response.json()
        return repo_data.get('private', True)  # Default to True if can't determine
    except Exception as e:
        logger.warning(f"Error checking repo visibility: {str(e)}")
        return True  # Default to True for safety

def get_pr_contents(repo_url: str, pr_number: int, github_token: str = None) -> Dict[str, Any]:
    """
    Fetch PR contents from GitHub using requests
    Returns a dictionary with PR data or error message
    """
    try:
        # Parse repo owner and name from URL
        try:
            _, _, _, owner, repo = repo_url.rstrip('/').split('/')
        except ValueError:
            raise ValueError(f"Invalid repository URL format: {repo_url}")

        # Check if repo is private
        is_private = check_repo_visibility(owner, repo)
        
        # Set up headers based on repo visibility
        headers = {'Accept': 'application/vnd.github.v3+json'}
        if is_private:
            token = github_token or os.getenv('GITHUB_TOKEN')
            if not token:
                raise ValueError("GitHub token required for private repository access")
            headers['Authorization'] = f'token {token}'
        
        base_url = f'https://api.github.com/repos/{owner}/{repo}'
        pr_url = f'{base_url}/pulls/{pr_number}'
        
        logger.info(f"Fetching PR from GitHub: {pr_url}")
        pr_response = requests.get(pr_url, headers=headers)
        
        # Handle different error cases
        if pr_response.status_code == 404:
            raise ValueError("Pull request not found")
        elif pr_response.status_code == 401:
            if is_private:
                raise ValueError("Invalid GitHub token or insufficient permissions")
            else:
                raise ValueError("This repository requires authentication")
        elif pr_response.status_code == 403:
            raise ValueError("Rate limit exceeded or access denied")
            
        pr_response.raise_for_status()
        pr_data = pr_response.json()
        
        # Validate PR data
        if not pr_data:
            raise ValueError("Empty response from GitHub API")
        
        files_url = f'{pr_url}/files'
        files_response = requests.get(files_url, headers=headers)
        files_response.raise_for_status()
        files_data = files_response.json()
        
        # Construct response with default values for missing fields
        result = {
            'title': pr_data.get('title', 'Untitled PR'),
            'description': pr_data.get('body', '') or '',
            'files': [{
                'name': file.get('filename', 'unnamed_file'),
                'patch': file.get('patch', ''),
                'status': file.get('status', 'unknown')
            } for file in files_data if file.get('filename')]
        }
        
        if not result['files']:
            raise ValueError("No valid files found in PR")
            
        logger.info(f"Successfully fetched PR contents from {'private' if is_private else 'public'} repository")
        return result
        
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "401" in error_msg and not github_token:
            error_msg = "Repository is private and requires authentication. Please provide a GitHub token."
        logger.error(f"GitHub API request failed: {error_msg}")
        return {'error': f"GitHub API request failed: {error_msg}"}
    except Exception as e:
        logger.error(f"Error fetching PR contents: {str(e)}")
        return {'error': str(e)}

def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Count the number of tokens in a text string."""
    try:
        enc = encoding_for_model(model)
        return len(enc.encode(text))
    except Exception as e:
        logger.warning(f"Error counting tokens: {str(e)}")
        return len(text) // 4  # Rough estimation as fallback

def chunk_pr_contents(pr_contents: Dict[str, Any], max_tokens: int = 6000) -> List[Dict[str, Any]]:
    """Split PR contents into chunks that fit within token limits."""
    chunks = []
    current_chunk = {
        'title': pr_contents.get('title', 'Untitled PR'),
        'description': pr_contents.get('description', ''),
        'files': []
    }
    
    current_tokens = count_tokens(current_chunk['title'] + current_chunk['description'])
    
    for file in pr_contents.get('files', []):
        file_content = f"File: {file['name']}\nChanges:\n{file['patch']}"
        file_tokens = count_tokens(file_content)
        
        if current_tokens + file_tokens > max_tokens and current_chunk['files']:
            chunks.append(current_chunk)
            current_chunk = {
                'title': pr_contents['title'],
                'description': '',
                'files': [file]
            }
            current_tokens = count_tokens(current_chunk['title']) + file_tokens
        else:
            current_chunk['files'].append(file)
            current_tokens += file_tokens
    
    if current_chunk['files']:
        chunks.append(current_chunk)
    
    return chunks or [current_chunk]  # Return at least one chunk

def analyze_code_with_openai(pr_contents: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze PR contents using OpenAI"""
    try:
        chunks = chunk_pr_contents(pr_contents)
        all_analyses = []
        
        for i, chunk in enumerate(chunks):
            prompt = f"""
            Analyze these changes (part {i+1}/{len(chunks)}):
            PR Title: {chunk['title']}
            
            Changes to analyze:
            """
            
            for file in chunk['files']:
                prompt += f"\nFile: {file['name']}\nChanges:\n{file['patch']}\n"
            
            prompt += """
            Please review the code for:
            1. Critical issues (syntax errors, security vulnerabilities)
            2. Performance concerns
            3. Code quality issues
            4. Best practice violations
            
            Format each issue as:
            Type: (line number) - Description - Suggested fix
            """

            if i > 0:
                time.sleep(20)  # Rate limiting
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert code reviewer. Focus on critical issues and provide clear, actionable feedback."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            
            all_analyses.append(response.choices[0].message['content'])
        
        return format_analysis_results(pr_contents['files'], "\n\n".join(all_analyses))
        
    except Exception as e:
        logger.error(f"Error in OpenAI analysis: {str(e)}")
        return {'error': str(e)}

def format_analysis_results(files: List[Dict[str, Any]], analysis: str) -> Dict[str, Any]:
    """Format the analysis results into the required structure"""
    try:
        issues = []
        
        # Enhanced regex pattern to capture more issue formats
        patterns = [
            r"(?P<type>error|warning|issue|critical):\s*(?:line\s*)?(?P<line>\d+)\s*-\s*(?P<description>[^-]+)(?:\s*-\s*(?P<solution>.+))?",
            r"(?P<type>error|warning|issue|critical):\s*(?P<description>[^(]+)\s*\(line\s*(?P<line>\d+)\)(?:\s*-\s*(?P<solution>.+))?"
        ]
        
        # Try each pattern
        for pattern in patterns:
            matches = re.finditer(pattern, analysis, re.IGNORECASE)
            for match in matches:
                issues.append({
                    "type": match.group("type").capitalize(),
                    "line": int(match.group("line")),
                    "description": match.group("description").strip(),
                    "suggestion": (match.group("solution") or "See description for details").strip()
                })
        
        # If no specific issues found, create a general analysis
        if not issues:
            # Split analysis into paragraphs and create separate issues
            paragraphs = [p.strip() for p in analysis.split('\n\n') if p.strip()]
            issues = [{
                "type": "Analysis",
                "line": 0,
                "description": paragraph,
                "suggestion": "See description for details"
            } for paragraph in paragraphs]
        
        # Group issues by file
        files_with_issues = []
        for file in files:
            file_name = file['name']
            file_issues = [
                issue for issue in issues 
                if issue['line'] > 0 and (
                    re.search(rf"\b{re.escape(file_name)}\b", issue['description'], re.IGNORECASE) or
                    len(files) == 1  # If only one file, assign all issues to it
                )
            ]
            
            # Add file-specific issues or a "no issues" entry
            files_with_issues.append({
                "name": file_name,
                "issues": file_issues or [{
                    "type": "Info",
                    "line": 0,
                    "description": "No specific issues detected",
                    "suggestion": "No action needed"
                }]
            })
        
        # Generate summary
        total_issues = len([i for i in issues if i['type'].lower() not in ['info', 'analysis']])
        critical_issues = len([i for i in issues if i['type'].lower() in ['error', 'critical']])
        
        return {
            "files": files_with_issues,
            "summary": {
                "total_files": len(files),
                "total_issues": total_issues,
                "critical_issues": critical_issues
            }
        }
        
    except Exception as e:
        logger.error(f"Error formatting analysis results: {str(e)}")
        return {
            "files": [],
            "summary": {
                "total_files": 0,
                "total_issues": 0,
                "critical_issues": 0
            },
            "error": str(e)
        }

@celery.task(bind=True, name='app.celery_worker.process_pr')
def process_pr(self, repo_url: str, pr_number: int, github_token: str = None) -> Dict[str, Any]:
    """Process PR analysis as a Celery task"""
    task_id = self.request.id
    logger.info(f"Starting analysis for PR {pr_number} from {repo_url} (Task ID: {task_id})")
    
    try:
        # Fetch PR contents
        pr_contents = get_pr_contents(repo_url, pr_number, github_token)
        
        if 'error' in pr_contents:
            logger.error(f"Error fetching PR contents: {pr_contents['error']} (Task ID: {task_id})")
            return {
                'status': 'failed',
                'task_id': task_id,
                'error': f"PR Content Error: {pr_contents['error']}",
                'state': 'FAILURE'
            }
        
        # Validate PR contents
        if not pr_contents.get('files'):
            return {
                'status': 'failed',
                'task_id': task_id,
                'error': 'No files found in PR',
                'state': 'FAILURE'
            }
        
        logger.info(f"Successfully fetched PR contents (Task ID: {task_id})")
        
        # Analyze with OpenAI
        analysis_results = analyze_code_with_openai(pr_contents)
        
        if 'error' in analysis_results:
            logger.error(f"Error analyzing code: {analysis_results['error']} (Task ID: {task_id})")
            return {
                'status': 'failed',
                'task_id': task_id,
                'error': f"Analysis Error: {analysis_results['error']}",
                'state': 'FAILURE'
            }
        
        logger.info(f"Successfully analyzed PR contents (Task ID: {task_id})")
        
        return {
            'status': 'completed',
            'task_id': task_id,
            'result': analysis_results,
            'state': 'SUCCESS'
        }
        
    except Exception as e:
        logger.error(f"Error processing PR: {str(e)} (Task ID: {task_id})")
        return {
            'status': 'failed',
            'task_id': task_id,
            'error': str(e),
            'state': 'FAILURE'
        }

@celery.task(name='app.celery_worker.test_task')
def test_task():
    """Simple test task to verify Celery is working"""
    logger.info("Test task is running")
    return {
        'status': 'completed',
        'message': "Test task completed successfully"
    }

if __name__ == '__main__':
    logger.info("Celery worker module loaded successfully")