#!/bin/bash
# ============================================================
# Wolf Chat - Chroma MCP Installation Script (Linux/macOS)
# ============================================================
# This script:
# 1. Creates a temporary download folder
# 2. Downloads chroma_mcp-0.2.6-py3-none-any.whl
# 3. Installs the package using UV
# 4. Cleans up temporary files
# ============================================================

# Navigate to project root (script is in scripts/ folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || exit 1

echo ""
echo "============================================================"
echo "Chroma MCP Installation"
echo "============================================================"
echo ""

# Define download URL and temporary folder
DOWNLOAD_URL="https://github.com/chroma-core/chroma-mcp/releases/download/v0.2.6/chroma_mcp-0.2.6-py3-none-any.whl"
TEMP_FOLDER="temp_chroma_install"
WHL_FILE="chroma_mcp-0.2.6-py3-none-any.whl"

# Check if UV is installed
echo "[1/5] Checking UV installation..."
if ! command -v uv &> /dev/null; then
    echo ""
    echo "ERROR: UV is not installed"
    echo "Please install UV first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    exit 1
fi
echo "UV found:"
uv --version
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo ""
    echo "ERROR: Virtual environment not found at '.venv/'"
    echo "Please run scripts/setup_uv_env.sh first to create the environment"
    echo ""
    exit 1
fi
echo "[2/5] Virtual environment found at '.venv/'"
echo ""

# Create temporary folder
echo "[3/5] Creating temporary download folder..."
if [ -d "$TEMP_FOLDER" ]; then
    echo "Cleaning existing temporary folder..."
    rm -rf "$TEMP_FOLDER"
fi
mkdir -p "$TEMP_FOLDER"
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to create temporary folder"
    echo ""
    exit 1
fi
echo "Temporary folder created: $TEMP_FOLDER"
echo ""

# Download the .whl file
echo "[4/5] Downloading Chroma MCP package..."
echo "URL: $DOWNLOAD_URL"
echo ""
echo "This may take a moment depending on your internet connection..."
echo ""

# Use curl or wget to download the file
if command -v curl &> /dev/null; then
    curl -L -o "$TEMP_FOLDER/$WHL_FILE" "$DOWNLOAD_URL"
    DOWNLOAD_STATUS=$?
elif command -v wget &> /dev/null; then
    wget -O "$TEMP_FOLDER/$WHL_FILE" "$DOWNLOAD_URL"
    DOWNLOAD_STATUS=$?
else
    echo ""
    echo "ERROR: Neither curl nor wget is installed"
    echo "Please install curl or wget to download the package"
    echo ""
    rm -rf "$TEMP_FOLDER"
    exit 1
fi

if [ $DOWNLOAD_STATUS -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to download the package"
    echo "Please check your internet connection and try again"
    echo ""
    rm -rf "$TEMP_FOLDER"
    exit 1
fi

if [ ! -f "$TEMP_FOLDER/$WHL_FILE" ]; then
    echo ""
    echo "ERROR: Downloaded file not found"
    echo ""
    rm -rf "$TEMP_FOLDER"
    exit 1
fi

echo "Download completed successfully"
echo "File location: $TEMP_FOLDER/$WHL_FILE"
echo ""

# Install the package using UV
echo "[5/5] Installing Chroma MCP package with UV..."
echo ""

uv pip install "$TEMP_FOLDER/$WHL_FILE"

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install Chroma MCP"
    echo "The downloaded file is preserved in $TEMP_FOLDER for manual inspection"
    echo ""
    exit 1
fi

echo ""
echo "============================================================"
echo "Installation completed successfully!"
echo "============================================================"
echo ""
echo "Chroma MCP v0.2.6 has been installed to your virtual environment"
echo ""

# Clean up temporary folder
echo "Cleaning up temporary files..."
rm -rf "$TEMP_FOLDER"
echo "Temporary files removed"
echo ""

# Verify installation
echo "Verifying installation..."
if uv pip list | grep -i "chroma-mcp" &> /dev/null; then
    echo ""
    echo "Package verification successful:"
    uv pip list | grep -i "chroma"
    echo ""
else
    echo ""
    echo "WARNING: Package installed but not found in package list"
    echo "This may be normal - please verify manually if needed"
    echo ""
fi

echo "============================================================"
echo ""
echo "To use Chroma MCP, configure it in your MCP servers setup"
echo "See config.py for MCP server configuration examples"
echo ""
echo "============================================================"
exit 0
