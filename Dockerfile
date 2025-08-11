# Docker Configuration for EasyRec API

FROM mybigpai-public-registry.cn-beijing.cr.aliyuncs.com/easyrec/easyrec:py36-tf1.15-0.8.5

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app/

# Install additional dependencies
RUN pip install flask flask-cors gunicorn

# Create necessary directories
RUN mkdir -p models/checkpoints models/export logs data

# Generate sample data
RUN python data/process_data.py

# Expose port
EXPOSE 5000

# Set environment variables
ENV MODEL_DIR=/app/models/checkpoints/deepfm_movies
ENV CONFIG_PATH=/app/config/deepfm_config.prototxt
ENV PORT=5000

# Run the application
CMD ["python", "scripts/serve.py"]
