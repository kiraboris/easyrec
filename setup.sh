#!/bin/bash

# EasyRec Online Project Setup Script
# Sets up Alibaba EasyRec + Online Learning Extensions

set -e

echo "Setting up EasyRec Online - Real-time Recommendation System..."
echo "============================================================="

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Use the virtual environment's python and pip directly instead of sourcing
VENV_PYTHON="./venv/bin/python"
VENV_PIP="./venv/bin/pip"

# Upgrade pip
echo "Upgrading pip in virtual environment..."
$VENV_PIP install --upgrade pip

# Install requirements (excluding EasyRec for now)
echo "Installing Python dependencies..."
$VENV_PIP install -r requirements.txt

# Clone and install Alibaba EasyRec
echo "Cloning and installing Alibaba EasyRec framework..."
if [ ! -d "EasyRec" ]; then
    echo "Cloning Alibaba EasyRec repository..."
    git clone https://github.com/alibaba/EasyRec.git
fi

cd EasyRec
echo "Installing EasyRec dependencies..."
bash scripts/init.sh
echo "Installing EasyRec framework..."
$VENV_PYTHON setup.py install
cd ..

# Generate sample data
echo "Generating sample training data..."
$VENV_PYTHON data/process_data.py

# Create necessary directories
echo "Creating project directories..."
mkdir -p models/checkpoints/deepfm_movies
mkdir -p models/online/deepfm_movies
mkdir -p models/export/online
mkdir -p logs
mkdir -p streaming/data

echo ""
echo "🎉 EasyRec Online setup completed successfully!"
echo ""
echo "📁 Project Structure:"
echo "   - EasyRec/           # Alibaba EasyRec framework (cloned)"
echo "   - models/            # Model storage"
echo "   - streaming/         # Online learning components"
echo "   - api/               # REST API server"
echo "   - data/              # Training data"
echo ""
echo "🚀 Next steps:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Train base model: ./venv/bin/python scripts/train.py --config config/deepfm_config.prototxt"
echo "3. Start API server: ./venv/bin/python api/app.py"
echo "4. Test online features: ./venv/bin/python scripts/online_train.py --mode test"
echo ""
echo "🌐 API will be available at: http://localhost:5000"
echo "📊 Online learning endpoints: http://localhost:5000/online/*"
