FROM python:3.11-slim

WORKDIR /app

# Install Node.js and npm
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install resume-cli globally
RUN npm install -g resume-cli jsonresume-theme-stackoverflow

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PORT=8080

# Run the application
CMD ["python", "app.py"] 