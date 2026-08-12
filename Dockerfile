FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Playwright browsers are only needed for live NSE scraping at runtime,
# not for tests. Install them separately when running live dashboards.
RUN python -m playwright install --with-deps chromium > /dev/null 2>&1 || true

CMD ["python", "test_all.py"]
