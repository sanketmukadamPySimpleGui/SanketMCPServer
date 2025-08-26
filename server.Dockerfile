# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server application code
COPY fastmcp_quickstart.py .
COPY database.py .

# The port the app runs on. This is for documentation; the actual port is set in the CMD.
EXPOSE 8000

# Run the application using the SSE transport
CMD ["python", "fastmcp_quickstart.py", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]