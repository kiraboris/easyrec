#!/bin/bash

# Quick start script for EasyRec project

set -e

echo "EasyRec Quick Start"
echo "==================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running setup..."
    bash setup.sh
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if data exists
if [ ! -f "data/movies_train_data.csv" ]; then
    echo "Generating sample data..."
    python data/process_data.py
fi

# Check if we want to train a new model
if [ "$1" = "train" ] || [ ! -d "models/checkpoints/deepfm_movies" ]; then
    echo "Training model..."
    python scripts/train.py --config config/deepfm_config.prototxt --mode train
fi

# Start the API server
echo "Starting API server..."
echo "API will be available at: http://localhost:5000"
echo "Press Ctrl+C to stop the server"

python api/app.py
