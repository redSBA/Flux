FROM python:3.11-slim

WORKDIR /app

# Устанавливаем build tools для компиляции пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Обновляем pip
RUN pip install --upgrade pip setuptools wheel

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем бота
COPY main.py .

# Запускаем бота
CMD ["python", "main.py"]
