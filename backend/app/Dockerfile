FROM python:3.11.7-slim

# PyPI mirror for faster builds in CN networks; harmless elsewhere.
RUN pip config set global.index-url https://mirrors.cernet.edu.cn/pypi/web/simple && \
    pip install --no-cache-dir --upgrade pip

WORKDIR /app

# Pure-Python / manylinux-wheel dependencies only: no compiler toolchain needed.
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x /app/start.sh

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "app_main:app", "--host", "0.0.0.0", "--port", "8000"]
