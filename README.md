# PR Analysis Tool

This project is a PR analysis tool that uses FastAPI and Celery to analyze pull requests from GitHub. It leverages OpenAI's API to provide insights into code changes.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [Running Celery Worker](#running-celery-worker)

## Prerequisites

- Python 3.9 or higher
- pip (Python package installer)
- Redis (for Celery backend)
- GitHub account (for accessing repositories)

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/potpie.git
   cd potpie
   ```

2. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:

   ```bash
   pip install -r requirements.txt
   ```

## Environment Variables

Create a `.env` file in the root of the project and add the following variables:
OPENAI_API_KEY="your_openai_api_key"
REDIS_URL="redis://default:your_redis_password@your_redis_host:6379"
GITHUB_TOKEN="your_github_token" # Optional, only needed for private repositories


## Running the Application

1. Start the FastAPI application:

   ```bash
   python run.py
   ```

   The application will be available at `http://localhost:8080`.

## Running Celery Worker

1. Open a new terminal window (keep the FastAPI application running).
2. Start the Celery worker:

   ```bash
   celery -A app.celery_worker worker --loglevel=info
   ```

   This will start the Celery worker that processes the tasks.


