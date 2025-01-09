from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import openai
from dotenv import load_dotenv
import requests
import logging

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')
logger.info("OpenAI API key configured")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def analyze_code(pr_contents):
    """Analyze PR contents using OpenAI"""
    try:
        prompt = f"""
        Review the following code changes from PR: {pr_contents['title']}
        
        For each file, analyze the changes and provide:
        1. Potential bugs
        2. Security issues
        3. Performance concerns
        4. Code style improvements
        
        Format each issue as:
        FILE: <filename>
        LINE: <line_number>
        TYPE: <bug|security|performance|style>
        ISSUE: <brief description>
        FIX: <suggested solution>
        """
        
        for file in pr_contents['files']:
            prompt += f"\n\nFile: {file['name']}\nChanges:\n{file['patch']}"
        
        logger.info("Sending request to OpenAI for analysis")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a code reviewer. Be specific and concise."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        logger.info("Received response from OpenAI")
        return {"analysis": response.choices[0].message['content']}
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
        return {'error': str(e)}

def get_pr_contents(repo_url: str, pr_number: int, github_token: str = None):
    """Fetch PR contents from GitHub"""
    try:
        token = github_token or os.getenv('GITHUB_TOKEN')
        headers = {'Authorization': f'token {token}'} if token else {}
        
        _, _, _, owner, repo = repo_url.rstrip('/').split('/')
        
        pr_url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}'
        logger.info(f"Fetching PR from GitHub: {pr_url}")
        pr_response = requests.get(pr_url, headers=headers)
        pr_data = pr_response.json()
        
        if 'message' in pr_data and pr_data['message'] == 'Not Found':
            logger.error("Pull request not found")
            raise Exception('Pull request not found')
        
        files_url = f'{pr_url}/files'
        files_response = requests.get(files_url, headers=headers)
        files_data = files_response.json()
        
        logger.info("Successfully fetched PR contents")
        return {
            'title': pr_data['title'],
            'description': pr_data['body'] or '',
            'files': [{
                'name': file['filename'],
                'patch': file.get('patch', ''),
                'status': file['status']
            } for file in files_data]
        }
    except Exception as e:
        logger.error(f"Error fetching PR contents: {str(e)}")
        return {'error': str(e)}

@app.post("/")
async def analyze(request: Request):
    """Main analyze endpoint"""
    logger.info("Analyze endpoint called")
    try:
        body = await request.json()
        logger.info(f"Received request body: {body}")
        
        repo_url = body.get('repo_url')
        pr_number = body.get('pr_number')
        github_token = body.get('github_token')

        if not repo_url or not pr_number:
            logger.error("Missing required parameters")
            raise HTTPException(status_code=400, detail="Missing required parameters")

        logger.info(f"Processing PR {pr_number} from {repo_url}")
        pr_contents = get_pr_contents(repo_url, pr_number, github_token)
        
        if 'error' in pr_contents:
            logger.error(f"Error fetching PR contents: {pr_contents['error']}")
            raise HTTPException(status_code=400, detail=pr_contents['error'])
        
        analysis_results = analyze_code(pr_contents)
        
        if 'error' in analysis_results:
            logger.error(f"Error analyzing code: {analysis_results['error']}")
            raise HTTPException(status_code=500, detail=analysis_results['error'])

        logger.info("Analysis completed successfully")
        return {
            "status": "success",
            "data": analysis_results
        }
    except Exception as e:
        logger.error(f"Error in analyze endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 