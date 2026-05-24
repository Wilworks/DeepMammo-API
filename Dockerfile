# ── Base image ────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────
# libgl1       : OpenCV needs this for image processing
# libglib2.0-0 : OpenCV dependency
# libgomp1     : onnxruntime parallel execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────
# Copy requirements first — Docker layer caches this separately from code.
# So if only your code changes, pip install is skipped on rebuild. Fast.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────────
COPY . .

# ── Collect static files ──────────────────────────────────────────────
RUN python manage.py collectstatic --noinput

# ── Create model directory (ONNX file tracked via Git LFS) ────────────
RUN mkdir -p model

# ── Expose port ───────────────────────────────────────────────────────
# Hugging Face Spaces routes all traffic to port 7860
EXPOSE 7860

# ── Start server ──────────────────────────────────────────────────────
# gunicorn: production WSGI server (not Django's dev server)
# --workers 1 : HF free tier has limited RAM, 1 worker is safe
# --timeout 120: inference can take up to 30s, give it headroom
# --log-level info: see what's happening in HF logs
CMD ["gunicorn", "core.wsgi:application", \
     "--bind", "0.0.0.0:7860", \
     "--workers", "1", \
     "--timeout", "120", \
     "--log-level", "info"]
