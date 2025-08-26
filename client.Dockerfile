# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the client application and its assets
COPY clients.py .
COPY static ./static
COPY templates ./templates

# Expose the port the app runs on
EXPOSE 8000

# Run the Uvicorn server, making it accessible from outside the container
CMD ["uvicorn", "clients:app", "--host", "0.0.0.0", "--port", "8000"]