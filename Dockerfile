# 构建Python依赖
FROM python:3.10-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --progress-bar off -r requirements.txt

# 生产镜像
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends libopus0 ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 从构建阶段复制Python包
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# 复制应用代码
COPY . .

RUN mkdir -p tmp data /.mem0 && chmod 777 tmp data /.mem0

# 启动应用
CMD ["python", "app.py"]