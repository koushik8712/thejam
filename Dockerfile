FROM python:3.9-slim

# Install MySQL development libraries and build tools
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \ 
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# MySQL development libraries
# Tools for compiling Python packages

# Create a virtual environment and install Python dependencies
RUN --mount=type=cache,id=s/fe70864d-55a4-4c52-bf01-f3326a5413d2-/root/cache/pip,target=/root/.cache/pip python -m venv --copies /opt/venv && . /opt/venv/bin/activate && pip install -r requirements.txt