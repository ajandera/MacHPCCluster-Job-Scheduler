#!/bin/bash
set -e

# macOS HPC Cluster Installation Script
# This script sets up OpenMPI and required dependencies on macOS

echo "======================================"
echo "macOS HPC Cluster Setup"
echo "======================================"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Error: This script is for macOS only"
    exit 1
fi

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew already installed"
fi

# Update Homebrew
echo "Updating Homebrew..."
brew update

# Install OpenMPI
echo "Installing OpenMPI..."
brew install open-mpi

# Install Python 3
echo "Installing Python 3..."
brew install python

# Install required Python packages
echo "Installing Python packages..."
pip3 install --upgrade pip
pip3 install numpy mpi4py pyobjc-framework-Metal

# Verify OpenMPI installation
echo ""
echo "======================================"
echo "Verifying Installation"
echo "======================================"
mpirun --version
echo ""
python3 --version
echo ""

# Create project directories
echo "Creating project directories..."
mkdir -p jobs/running
mkdir -p jobs/finished
mkdir -p metal_kernels
mkdir -p examples

# Initialize job queue
if [ ! -f "jobs/queue.json" ]; then
    echo "[]" > jobs/queue.json
    echo "Initialized job queue"
fi

# Check for SSH key
echo ""
echo "======================================"
echo "SSH Configuration"
echo "======================================"
if [ -f "$HOME/.ssh/id_ed25519" ] || [ -f "$HOME/.ssh/id_rsa" ]; then
    echo "SSH key found"
else
    echo "No SSH key found. Generate one with:"
    echo "   ssh-keygen -t ed25519"
    echo ""
    echo "Then copy to remote nodes with:"
    echo "   ssh-copy-id user@remote-hostname"
fi

echo ""
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Configure hosts.txt with your cluster nodes"
echo "2. Set up passwordless SSH to all nodes"
echo "3. Run this script on ALL cluster nodes"
echo "4. Test with: mpirun --hostfile hosts.txt -np 2 hostname"
echo ""
echo "See README.md for detailed instructions"
echo ""