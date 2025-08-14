# Docker Configuration for EasyRec API with streaming support

FROM mybigpai-public-registry.cn-beijing.cr.aliyuncs.com/easyrec/easyrec:py36-tf1.15-0.8.5

# Set working directory
WORKDIR /app

# Copy requirement files first for caching (if separated; fallback to full copy later)
COPY requirements.txt /app/requirements.txt

# Install dependencies (ignore already satisfied to speed build)
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy project source
COPY . /app/

# Create necessary directories
RUN mkdir -p models/checkpoints models/export logs data

# Generate sample data (non-fatal if script already ran)
RUN python data/process_data.py || true

# Expose port
EXPOSE 5000

# Set environment variables
ENV MODEL_DIR=/app/models/checkpoints/deepfm_movies \
    CONFIG_PATH=/app/config/deepfm_config.prototxt \
    PORT=5000 \
    KAFKA_SERVERS=kafka:9092 \
    KAFKA_TOPIC=easyrec_training \
    KAFKA_GROUP=easyrec_online

# Default command launches Gunicorn server wrapper
CMD ["python", "scripts/serve.py"]
