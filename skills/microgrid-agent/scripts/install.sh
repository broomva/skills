#!/usr/bin/env bash
# =============================================================================
# Microgrid Agent — Installation Script for Raspberry Pi
# =============================================================================
# Usage:
#   sudo ./scripts/install.sh [--readonly]
#
# Flags:
#   --readonly   Set up a read-only root filesystem overlay (optional).
#                This protects the SD card from corruption on power loss.
# =============================================================================
set -euo pipefail

INSTALL_DIR="/opt/microgrid-agent"
DATA_DIR="/var/lib/microgrid-agent"
SERVICE_NAME="microgrid-agent"
VENV_DIR="${INSTALL_DIR}/venv"
READONLY_FLAG=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --readonly) READONLY_FLAG=true ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# -----------------------------------------------------------------------------
# Check prerequisites
# -----------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)."
    exit 1
fi

echo "=== Microgrid Agent Installer ==="
echo "Install directory: ${INSTALL_DIR}"
echo "Data directory:    ${DATA_DIR}"
echo "Read-only rootfs:  ${READONLY_FLAG}"
echo ""

# -----------------------------------------------------------------------------
# 1. Install system dependencies
# -----------------------------------------------------------------------------
echo ">>> Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    libmodbus-dev \
    libatlas-base-dev \
    sqlite3 \
    i2c-tools \
    watchdog \
    curl \
    jq

# Enable I2C if not already
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo ">>> Enabling I2C interface..."
    BOOT_CONFIG="/boot/config.txt"
    [ -f /boot/firmware/config.txt ] && BOOT_CONFIG="/boot/firmware/config.txt"
    echo "dtparam=i2c_arm=on" >> "${BOOT_CONFIG}"
fi

# -----------------------------------------------------------------------------
# 2. Create directories
# -----------------------------------------------------------------------------
echo ">>> Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${DATA_DIR}/db"
mkdir -p "${DATA_DIR}/models"
mkdir -p "${DATA_DIR}/logs"
mkdir -p "${DATA_DIR}/sync-queue"
mkdir -p "${DATA_DIR}/backups"

# -----------------------------------------------------------------------------
# 3. Copy application files
# -----------------------------------------------------------------------------
echo ">>> Copying application files..."
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Copy source, config, and schema
cp -r "${SCRIPT_DIR}/src" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/config" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/schema" "${INSTALL_DIR}/"

# Copy main entry point if it exists
[ -f "${SCRIPT_DIR}/main.py" ] && cp "${SCRIPT_DIR}/main.py" "${INSTALL_DIR}/"

# Copy pyproject.toml for reference
[ -f "${SCRIPT_DIR}/pyproject.toml" ] && cp "${SCRIPT_DIR}/pyproject.toml" "${INSTALL_DIR}/"

# Ensure example configs are present, but don't overwrite real configs
for f in site.toml devices.toml; do
    if [ ! -f "${INSTALL_DIR}/config/${f}" ]; then
        echo "    NOTE: ${f} not found. Copy from ${f%.toml}.example.toml and customize."
    fi
done

# -----------------------------------------------------------------------------
# 4. Create Python virtual environment and install dependencies
# -----------------------------------------------------------------------------
echo ">>> Setting up Python virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

echo ">>> Installing Python dependencies..."
pip install --upgrade pip setuptools wheel -q

# Install from pyproject.toml if available, otherwise install individually
if [ -f "${INSTALL_DIR}/pyproject.toml" ]; then
    pip install -e "${INSTALL_DIR}" -q
else
    pip install \
        pymodbus>=3.5 \
        paho-mqtt>=2.0 \
        scipy>=1.11 \
        toml>=0.10 \
        aiosqlite>=0.19 \
        aiohttp>=3.9 \
        -q
fi

# Install TFLite runtime if on ARM (Raspberry Pi)
ARCH=$(uname -m)
if [[ "${ARCH}" == "aarch64" || "${ARCH}" == "armv7l" ]]; then
    echo ">>> Installing TFLite runtime for ${ARCH}..."
    pip install tflite-runtime -q 2>/dev/null || \
        echo "    WARNING: tflite-runtime not available for ${ARCH}. Using rule-based dispatch only."
fi

deactivate

# -----------------------------------------------------------------------------
# 5. Install systemd service
# -----------------------------------------------------------------------------
echo ">>> Installing systemd service..."
cp "${SCRIPT_DIR}/deploy/microgrid-agent.service" "/etc/systemd/system/${SERVICE_NAME}.service"

# Create a dedicated system user if it doesn't exist
if ! id -u microgrid >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin microgrid
fi

# Grant access to serial ports and I2C
usermod -aG dialout,i2c,gpio microgrid 2>/dev/null || true

# Set ownership
chown -R microgrid:microgrid "${INSTALL_DIR}"
chown -R microgrid:microgrid "${DATA_DIR}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
echo "    Service installed and enabled. Start with: systemctl start ${SERVICE_NAME}"

# -----------------------------------------------------------------------------
# 6. Enable hardware watchdog
# -----------------------------------------------------------------------------
echo ">>> Configuring hardware watchdog..."
BOOT_CONFIG="/boot/config.txt"
[ -f /boot/firmware/config.txt ] && BOOT_CONFIG="/boot/firmware/config.txt"

if ! grep -q "dtparam=watchdog=on" "${BOOT_CONFIG}"; then
    echo "dtparam=watchdog=on" >> "${BOOT_CONFIG}"
fi

# Configure watchdog daemon
cat > /etc/watchdog.conf <<'WDCONF'
watchdog-device = /dev/watchdog
watchdog-timeout = 15
max-load-1 = 24
min-memory = 1
interval = 10
WDCONF

systemctl enable watchdog 2>/dev/null || true

# -----------------------------------------------------------------------------
# 7. Initialize the knowledge graph database
# -----------------------------------------------------------------------------
echo ">>> Initializing knowledge graph database..."
if [ -f "${INSTALL_DIR}/schema/knowledge-graph.sql" ]; then
    sqlite3 "${DATA_DIR}/db/knowledge.db" < "${INSTALL_DIR}/schema/knowledge-graph.sql"
    chown microgrid:microgrid "${DATA_DIR}/db/knowledge.db"
    echo "    Database initialized at ${DATA_DIR}/db/knowledge.db"
fi

# -----------------------------------------------------------------------------
# 8. (Optional) Read-only root filesystem overlay
# -----------------------------------------------------------------------------
if [ "${READONLY_FLAG}" = true ]; then
    echo ">>> Setting up read-only root filesystem overlay..."
    echo ""
    echo "    This creates an overlay filesystem so that the root partition is"
    echo "    mounted read-only, protecting the SD card from corruption. Writes"
    echo "    go to a tmpfs overlay and are lost on reboot. The data directory"
    echo "    (${DATA_DIR}) is bind-mounted read-write from a separate partition"
    echo "    or USB drive."
    echo ""

    # Install overlayroot if available
    apt-get install -y -qq overlayroot 2>/dev/null || true

    if command -v overlayroot-chroot >/dev/null 2>&1; then
        # Configure overlayroot
        sed -i 's/^overlayroot=""/overlayroot="tmpfs"/' /etc/overlayroot.conf 2>/dev/null || true
        echo "    overlayroot configured. Reboot to activate."
        echo "    WARNING: After reboot, use 'overlayroot-chroot' to make persistent changes."
    else
        echo "    WARNING: overlayroot package not available. Skipping read-only setup."
        echo "    You can manually configure /etc/fstab to mount / as read-only."
    fi

    # Ensure data directory has its own mount point entry in fstab
    if ! grep -q "${DATA_DIR}" /etc/fstab; then
        echo "    NOTE: Add a mount point for ${DATA_DIR} in /etc/fstab pointing to"
        echo "    a writable partition (e.g., USB drive or separate SD partition)."
    fi
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy config/site.example.toml -> config/site.toml and customize"
echo "  2. Copy config/devices.example.toml -> config/devices.toml and customize"
echo "  3. Place model files in ${DATA_DIR}/models/ (or use --simulate mode)"
echo "  4. Start the service: sudo systemctl start ${SERVICE_NAME}"
echo "  5. Check status: sudo systemctl status ${SERVICE_NAME}"
echo "  6. View logs: sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
