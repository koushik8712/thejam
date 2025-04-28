FROM python:3.9-slim

# Copy the requirements file into the image
COPY requirements.txt /app/requirements.txt

# Create a virtual environment and install Python dependencies
RUN --mount=type=cache,id=s/fe70864d-55a4-4c52-bf01-f3326a5413d2-/root/cache/pip,target=/root/.cache/pip python -m venv --copies /opt/venv && . /opt/venv/bin/activate && pip install -r /app/requirements.txt