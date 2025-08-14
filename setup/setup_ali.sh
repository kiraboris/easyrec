#!/bin/bash

set -e  # Exit on error


# Save current directory
SCRIPT_DIR=$(pwd)
cd ..
pwd

echo "Setting up original Alibaba EasyRec..."
echo "============================================================="

# Clone and install Alibaba EasyRec
echo "Cloning..."
if [ ! -d "EasyRec" ]; then
    echo "Cloning Alibaba EasyRec repository..."
    git clone https://github.com/alibaba/EasyRec.git
fi

cd EasyRec
pwd

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Use the virtual environment's python and pip directly instead of sourcing
VENV_PYTHON="./venv/bin/python"
VENV_PIP="./venv/bin/pip"

# Install requirements (excluding EasyRec for now)
echo "Installing Python dependencies..."
$VENV_PIP install -r $SCRIPT_DIR/requirements_ali.txt

# TODO: What else to consider?