# ==========================================
# Phase 1: 基础镜像与优化
# ==========================================
# 使用官方轻量级 Python 3.11 镜像
FROM python:3.11-slim

# 确保 Python 输出直接发送到终端 (Docker logs)
ENV PYTHONUNBUFFERED=1

# [UniMelb 大佬专享优化]：设置时区为墨尔本
# 这能保证日志时间对得上，且占星抽卡的 0 点刷新是澳洲时间。
ENV TZ=Australia/Melbourne
RUN apt-get update && apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 在容器内创建 /app 工作目录
WORKDIR /app


# ==========================================
# Phase 2: 依赖安装 (利用 Docker 缓存层)
# ==========================================
# 构建上下文在根目录，所以这里 COPY 根目录的 requirements.txt
COPY requirements.txt .

# 安装依赖，--no-cache-dir 减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt


# ==========================================
# Phase 3: 代码复制 (精准打击，排除噪音)
# ==========================================
# [重点修改]：不再使用 COPY . .
# 理由：我们必须排除巨大的 .venv/ 文件夹和需要持久化的 data/ 文件夹。
# 排除 .env 文件，Token 不应该打包进镜像，而是靠运行环境加载。

# 只复制核心代码文件
COPY main_bot.py .
COPY cogs/ ./cogs/

# 如果你建立了 utils 文件夹，这里也要解开注释
# COPY utils/ ./utils/

# [重要]：我们不在构建时复制 data 文件夹（包含 nodes.csv）
# 理由：data 需要在 docker-compose 运行时挂载，才能保证读写保存的数据不丢失。
# 镜像启动时，Docker Compose 会自动帮你处理好映射关系。


# ==========================================
# Phase 4: 启动与执行
# ==========================================
# 当容器启动时，指定要运行的命令
CMD ["python", "main_bot.py"]