FROM python:3.11-slim

WORKDIR /app

# Bağımlılıkları yükleyelim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tüm backend kodunu içeri aktaralım
COPY . .

EXPOSE 8000

# FastAPI uygulamasını ayağa kaldıralım
# Not: Eğer ana çalıştırma dosyan app/main.py içindeyse bu komut aynen kalır.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]