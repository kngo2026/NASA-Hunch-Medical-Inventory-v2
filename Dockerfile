FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libx11-6 \
    libxext6 \
    libgl1 \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libopenblas-dev \
    liblapack-dev \
    python3-dev \
    && pip install cmake==3.25.0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD gunicorn nasa.wsgi:application --bind 0.0.0.0:$PORT