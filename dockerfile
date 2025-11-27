# Use a lightweight Python base image
FROM python:3.9-slim

# 1. Install system dependencies: Tesseract OCR + Kannada Language Pack
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kan \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Set working directory
WORKDIR /app

# 3. Copy python requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of the application code
COPY . .

# 5. Expose the port (Cloud platforms often require this)
EXPOSE 5000

# 6. Run the application using Gunicorn (Production Server)
# "app:app" means "module_name:variable_name"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]