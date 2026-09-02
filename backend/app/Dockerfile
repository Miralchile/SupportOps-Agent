FROM python:3.11.7-slim

# Keep the package index configurable without coupling reproducible builds to
# one regional mirror. Override with ``--build-arg PIP_INDEX_URL=...`` when a
# private or regional index is required.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" --upgrade pip

WORKDIR /app

# Pure-Python / manylinux-wheel dependencies only: no compiler toolchain needed.
COPY requirements.txt /app/
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY . /app
RUN chmod +x /app/start.sh

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "app_main:app", "--host", "0.0.0.0", "--port", "8000"]
