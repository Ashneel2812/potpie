FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Ensure static directory exists and has correct permissions
RUN mkdir -p static && \
    chmod 755 static && \
    chmod 644 static/index.html

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 