# Python 3.11 versiyonunu temel al
FROM python:3.11-slim

# 1. Chrome ve Sürücüsünü (Chromedriver) zorla kur
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Çalışma klasörünü ayarla
WORKDIR /app

# Dosyaları kopyala
COPY . .

# Kütüphaneleri yükle
RUN pip install --no-cache-dir -r requirements.txt

# Chrome'un nerede olduğunu sisteme tanıt
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PORT=8080

# Uygulamayı başlat
CMD ["python", "app.py"]