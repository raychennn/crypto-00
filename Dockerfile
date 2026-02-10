FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（如需要）
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴文件
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案文件
COPY . .

# 建立數據目錄
RUN mkdir -p /app/data/results

# 設定環境變數（可在部署時覆蓋）
ENV PYTHONUNBUFFERED=1

# 暴露 Port（Telegram Bot 不需要，但保留以備將來使用）
# EXPOSE 8080

# 啟動應用
CMD ["python", "main.py"]
