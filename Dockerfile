# Annie as a container (used by Railway; runs anywhere Docker does).
#   docker build -t annie . && docker run -p 8501:8501 -e ADMIN_PIN=... annie
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract (OCR fallback) and the system libraries OpenCV/RapidOCR need - same list as packages.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# RapidOCR fetches its models on first use; do it now so the first scanned upload is not slow
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"

COPY . .

# Railway sets PORT; locally it falls back to 8501. The demo documents load on the first visit to an empty database.
EXPOSE 8501
# exec: Streamlit becomes PID 1, so it receives the platform's stop signal and shuts down cleanly
CMD ["sh", "-c", "exec streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
