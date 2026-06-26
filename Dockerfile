FROM python:3.11-slim

# Non-root user for defence-in-depth inside the container.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies before copying source so this layer is cached on re-builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Drop root privileges before the process starts.
USER appuser

EXPOSE 8000

# Single worker is enough for a stateless, I/O-bound API on the contest infra.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
