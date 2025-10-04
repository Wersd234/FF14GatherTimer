# 使用一个官方的、轻量级的 Python 3.11 镜像作为基础
FROM python:3.11-slim

# 在容器内创建一个名为 /app 的工作目录
WORKDIR /app

# 复制依赖列表文件到容器中
# (我们先复制这个文件并安装，因为依赖不经常变，Docker可以利用缓存加快后续构建)
COPY requirements.txt .

# 安装所有依赖库，--no-cache-dir 参数可以减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 将项目目录下的所有其他文件 (main_bot.py, cogs/, nodes.csv) 复制到容器的 /app 目录中
COPY . .

# 当容器启动时，指定要运行的命令
CMD ["python", "main_bot.py"]

# Ensures Python output is sent straight to terminal (Docker logs)
ENV PYTHONUNBUFFERED=1 