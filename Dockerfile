FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY ./app /app

CMD ["gunicorn", "--bind", "0.0.0.0:80", "main:app"]
