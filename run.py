import uvicorn

if __name__ == "__main__":
    # Use the import string for the app
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True) 