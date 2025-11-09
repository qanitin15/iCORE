FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ICORE_HOST=0.0.0.0 \
    ICORE_PORT=5000

WORKDIR /app

# install system deps for Pillow (if images are used)
RUN apt-get update && apt-get install -y build-essential libjpeg-dev zlib1g-dev --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# copy only requirements first for caching
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# copy project
COPY . /app

# ensure upload folder exists and has permission
RUN mkdir -p /app/static/uploads && chmod -R 755 /app/static/uploads

EXPOSE 5000

# use waitress to serve the WSGI app (backend:app)
CMD ["waitress-serve", "--listen=0.0.0.0:5000", "backend:app"]
