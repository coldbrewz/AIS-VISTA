FROM python:3.11-slim
WORKDIR /app

# Install dependencies including tzdata for timezone support
RUN apt-get update && apt-get install -y docker.io tzdata && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application files
COPY . .

# Run the FastAPI server
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-5001}"]
