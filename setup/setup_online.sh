#!/bin/bash

# EasyRec Online Project Setup Script
# Sets up Alibaba EasyRec + Online Learning Extensions

set -e

# Save current directory
SCRIPT_DIR=$(pwd)
cd ..
pwd

echo "Setting up EasyRec Online - Real-time Recommendation System..."
echo "============================================================="

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Use the virtual environment's python and pip directly instead of sourcing
VENV_PYTHON="./venv/bin/python"
VENV_PIP="./venv/bin/pip"


# Install requirements (excluding EasyRec for now)
echo "Installing Python dependencies..."
$VENV_PIP install -r $SCRIPT_DIR/requirements_online.txt


# Create necessary directories
echo "Creating project directories..."
mkdir -p models/checkpoints/deepfm_movies
mkdir -p models/online/deepfm_movies
mkdir -p models/export/online
mkdir -p logs
mkdir -p streaming/data
mkdir -p streaming/config

echo ""
echo "🎉 EasyRec Online setup completed successfully!"
echo ""
echo "📁 Project Structure:"
echo "   - ../EasyRec/        # Alibaba EasyRec framework (separately cloned)"
echo "   - models/            # Model storage"
echo "   - streaming/         # Online learning components"
echo "   - api/               # REST API server"
echo "   - logs/              # Log files"

echo ""
echo "🚀 Next steps:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Train base model and put it in models/checkpoints/"
echo "3. Start API server: ./venv/bin/python scripts/serve.py"
echo ""
echo "🌐 API will be available at: http://localhost:5000"
echo "📊 Online learning endpoints: http://localhost:5000/online/*"
