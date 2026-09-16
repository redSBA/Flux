FROM python:3.11-slim

WORKDIR /app

# Устанавливаем build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Обновляем pip
RUN pip install --upgrade pip setuptools wheel

# Копируем requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем бота
COPY main.py .

# Запускаем бота (с restart loop protection)
CMD ["python", "-u", "main.py"]
