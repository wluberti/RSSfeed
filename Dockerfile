FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user
RUN addgroup --system appgroup && adduser --system --group appuser

# Create data directory and set permissions
RUN mkdir -p data && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

EXPOSE 5050

CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--timeout", "120", "app:app"]
