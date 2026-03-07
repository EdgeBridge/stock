#!/bin/bash
# Install us-stock systemd services.
# Run: sudo bash deploy/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing us-stock systemd services..."

# Copy service files
sudo cp "$SCRIPT_DIR/usstock-backend.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/usstock-frontend.service" /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable usstock-backend.service
sudo systemctl enable usstock-frontend.service

echo ""
echo "Services installed. To start:"
echo "  sudo systemctl start usstock-backend"
echo "  sudo systemctl start usstock-frontend"
echo ""
echo "To check status:"
echo "  sudo systemctl status usstock-backend"
echo "  sudo systemctl status usstock-frontend"
echo ""
echo "Ports:"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:3001"
