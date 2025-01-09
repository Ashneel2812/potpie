from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
from app.celery_worker import process_pr
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = "static"  # Ensure this points to the correct directory
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def read_root():
    index_path = os.path.join(static_dir, "index.html")
    logger.info(f"Looking for index.html at: {index_path}")
    if os.path.exists(index_path):
        logger.info("Index file found, serving it.")
        return FileResponse(index_path, media_type='text/html')
    else:
        logger.error("Index file not found")
        raise HTTPException(status_code=404, detail="Index file not found")

class PRRequest(BaseModel):
    repo_url: str
    pr_number: int
    github_token: Optional[str] = None

@app.post("/api/analyze")
async def analyze_pr(request: PRRequest):
    logger.info(f"Received analyze request: {request.json()}")
    # Submit task to Celery
    task = process_pr.delay(
        repo_url=request.repo_url,
        pr_number=request.pr_number,
        github_token=request.github_token
    )
    logger.info(f"Task submitted with ID: {task.id}")
    return {"task_id": task.id}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    logger.info(f"Checking status for task ID: {task_id}")
    task = process_pr.AsyncResult(task_id)
    
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'result': task.result
        }
    else:
        response = {
            'state': task.state,
            'error': str(task.info),  # this will be the error raised
        }
    
    logger.info(f"Task status response: {response}")
    return response

@app.get("/api/results/{task_id}")
async def get_results(task_id: str):
    logger.info(f"Fetching results for task ID: {task_id}")
    task = process_pr.AsyncResult(task_id)
    if task.state == 'SUCCESS':
        logger.info(f"Results found for task ID: {task_id}")
        return task.result
    else:
        logger.warning(f"Results not ready for task ID: {task_id}")
        raise HTTPException(status_code=404, detail="Results not ready")

@app.get("/test_celery")
async def test_celery():
    """Test endpoint to verify Celery is working"""
    task = process_pr.delay(
        repo_url="https://github.com/test/repo",
        pr_number=1,
        github_token=None
    )
    logger.info(f"Test task created with ID: {task.id}")
    return {"message": "Test task created", "task_id": task.id}

@app.get("/debug/routes")
async def debug_routes():
    """List all registered routes"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": [method for method in route.methods] if route.methods else []
        })
    logger.info(f"Registered routes: {routes}")
    return {"routes": routes}

@app.get("/debug/static")
async def debug_static():
    """Debug static files setup"""
    try:
        logger.info("Debugging static files setup.")
        return {
            "static_dir": static_dir,
            "static_dir_exists": os.path.exists(static_dir),
            "index_path": os.path.join(static_dir, "index.html"),
            "index_exists": os.path.exists(os.path.join(static_dir, "index.html")),
            "current_dir": os.getcwd(),
            "files_in_static": os.listdir(static_dir) if os.path.exists(static_dir) else []
        }
    except Exception as e:
        logger.error(f"Error during static files debug: {str(e)}")
        return {"error": str(e)} 