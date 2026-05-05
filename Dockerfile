FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

# Copy project
COPY . /app

# Use stable python and upgrade pip
RUN python -m pip install --upgrade pip setuptools wheel

# Install Python dependencies
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# Install Playwright browsers (image may already include them)
RUN python -m playwright install --with-deps || true

ENV PYTHONUNBUFFERED=1

# Default command runs tests
CMD ["/bin/bash", "./run_tests.sh"]
