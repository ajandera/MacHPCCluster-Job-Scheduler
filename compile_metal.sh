#!/bin/bash
set -e

echo "🔨 Compiling Metal kernels..."

cd metal_kernels

# Compile Metal source to AIR (Apple Intermediate Representation)
xcrun -sdk macosx metal -c metal_add.metal -o metal_add.air

# Link AIR to metallib (Metal Library)
xcrun -sdk macosx metallib metal_add.air -o metal_add.metallib

# Clean up intermediate files
rm metal_add.air

echo "✅ Metal kernels compiled successfully!"
echo "   Output: metal_kernels/metal_add.metallib"

cd ..

# Test Metal availability
echo ""
echo "🧪 Testing Metal GPU availability..."
python3 metal_compute.py