FROM python:3.11.7-slim

# 使用清华大学镜像源
RUN echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

# 安装必要的构建工具和依赖
RUN apt-get update --fix-missing || apt-get update && \
    apt-get install -y --no-install-recommends --fix-missing \
    build-essential \
    cmake \
    g++ \
    python3-dev \
    make \
    libgl1 \
    libgl1-mesa-glx \
    libglu1-mesa \
    libglib2.0-0 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 配置 pip 镜像源并升级工具
RUN pip config set global.index-url https://mirrors.cernet.edu.cn/pypi/web/simple && \
    pip config set global.extra-index-url "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple" && \
    pip install --upgrade pip setuptools wheel

# 设置工作目录
WORKDIR /app

# ========== 分层安装依赖，最大化利用缓存 ==========

# 第1层：最小基础包（几乎永远不变）
COPY requirements-minimal.txt /app/
RUN pip install --no-cache-dir -r requirements-minimal.txt

# 第2层：Web框架（偶尔变化）
COPY requirements-web.txt /app/
RUN pip install --no-cache-dir -r requirements-web.txt

# 第3层：数据库驱动（很少变化）
COPY requirements-db.txt /app/
RUN pip install --no-cache-dir -r requirements-db.txt

# 第4层：LLM基础包（偶尔变化）
COPY requirements-llm-base.txt /app/
RUN pip install --no-cache-dir -r requirements-llm-base.txt

# 第5层：LLM大包（很少变化）
COPY requirements-llm-heavy.txt /app/
RUN pip install --no-cache-dir -r requirements-llm-heavy.txt

# 第6层：机器学习包（很少变化）
COPY requirements-ml.txt /app/
RUN pip install --no-cache-dir -r requirements-ml.txt

# 第7层：NLP处理包（很少变化）
COPY requirements-nlp.txt /app/
RUN pip install --no-cache-dir -r requirements-nlp.txt

# 第8层：图像处理包（很少变化）
COPY requirements-image.txt /app/
RUN pip install --no-cache-dir -r requirements-image.txt

# 第9层：文档处理包（很少变化）
COPY requirements-docs.txt /app/
RUN pip install --no-cache-dir -r requirements-docs.txt

# 设置 NLTK 数据路径
ENV NLTK_DATA=/usr/local/nltk_data
RUN python -c "import nltk; nltk.download('stopwords', download_dir='/usr/local/nltk_data'); nltk.download('punkt', download_dir='/usr/local/nltk_data'); nltk.download('punkt_tab', download_dir='/usr/local/nltk_data'); nltk.download('wordnet', download_dir='/usr/local/nltk_data')"

# 拷贝代码（这层总是会变化，但放在最后）
COPY . /app

# 修改文件权限
RUN chmod -R 755 /app && \
    chmod +x /app/start.sh 2>/dev/null || true

# 设置启动脚本为入口点
ENTRYPOINT ["/app/start.sh"]
