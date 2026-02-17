FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user with a fixed UID (1000) to match host user
ARG UID=1000
ARG GID=1000
RUN groupadd -g "${GID}" appgroup && \
    useradd -m -u "${UID}" -g "${GID}" -s /bin/bash appuser

# Create data directory and set permissions
RUN mkdir -p data && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

EXPOSE 5050

CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--timeout", "120", "app:app"]
