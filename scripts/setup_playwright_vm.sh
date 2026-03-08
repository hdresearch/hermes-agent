#!/bin/bash
# Setup a Vers VM with Playwright pre-installed
# Run this once to create a reusable VM

set -e

VM_NAME="hermes-playwright"
VM_ID_FILE="$HOME/.hermes/playwright_vm_id"

echo "🚀 Creating Vers VM with Playwright..."

# Check if vers CLI is installed
if ! command -v vers &> /dev/null; then
    echo "❌ vers CLI not found. Install with: go install github.com/verscloud/vers@latest"
    exit 1
fi

# Check if VERS_API_KEY is set
if [ -z "$VERS_API_KEY" ]; then
    if [ -f "$HOME/.hermes/.env" ]; then
        export $(grep VERS_API_KEY "$HOME/.hermes/.env" | xargs)
    fi
fi

if [ -z "$VERS_API_KEY" ]; then
    echo "❌ VERS_API_KEY not set"
    exit 1
fi

# Create VM from a vers.toml with playwright pre-installed
# First create a temporary directory with the vers.toml
TEMP_DIR=$(mktemp -d)
cat > "$TEMP_DIR/vers.toml" << 'EOF'
name = "hermes-playwright"
base = "ubuntu:24.04"

[vm]
vcpu = 2
memory = 4096
disk = 10240

[setup]
run = [
    "apt-get update -qq",
    "apt-get install -y -qq python3 python3-pip nodejs npm curl wget",
    "pip3 install playwright --break-system-packages",
    "playwright install chromium",
    "playwright install-deps chromium",
    "echo 'Playwright ready!'"
]
EOF

echo "📦 Building and running VM..."
cd "$TEMP_DIR"

# Run vers with the config
VM_OUTPUT=$(vers run -N "$VM_NAME" --vcpu-count 2 --mem-size 4096 --fs-size-vm 10240 2>&1) || {
    echo "Failed to create VM: $VM_OUTPUT"
    rm -rf "$TEMP_DIR"
    exit 1
}

echo "$VM_OUTPUT"

# Extract VM ID from output
VM_ID=$(echo "$VM_OUTPUT" | grep -oE "VM '[a-f0-9-]+'" | head -1 | tr -d "VM '")

if [ -z "$VM_ID" ]; then
    # Try alternative parsing
    VM_ID=$(vers list 2>/dev/null | grep "$VM_NAME" | awk '{print $1}' | head -1)
fi

if [ -z "$VM_ID" ]; then
    echo "❌ Could not determine VM ID"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "✅ VM created: $VM_ID"

# Save VM ID
mkdir -p "$(dirname "$VM_ID_FILE")"
echo "$VM_ID" > "$VM_ID_FILE"
echo "📝 VM ID saved to: $VM_ID_FILE"

# Wait for VM to be ready and install playwright
echo "⏳ Installing Playwright (this may take a few minutes)..."

# Wait a bit for VM to fully boot
sleep 10

# Install playwright
vers execute "$VM_ID" --timeout 300 -- bash -c "
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip nodejs npm curl wget > /dev/null 2>&1
    pip3 install playwright --break-system-packages > /dev/null 2>&1
    playwright install chromium > /dev/null 2>&1
    playwright install-deps chromium > /dev/null 2>&1
    echo 'PLAYWRIGHT_INSTALLED'
"

# Test that playwright works
echo "🧪 Testing Playwright..."
TEST_OUTPUT=$(vers execute "$VM_ID" --timeout 60 -- python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://example.com')
    print('SUCCESS:', page.title())
    browser.close()
" 2>&1)

if echo "$TEST_OUTPUT" | grep -q "SUCCESS:"; then
    echo "✅ Playwright is working!"
    echo "$TEST_OUTPUT"
else
    echo "❌ Playwright test failed:"
    echo "$TEST_OUTPUT"
fi

rm -rf "$TEMP_DIR"

echo ""
echo "🎉 Done! VM ID: $VM_ID"
echo "The VM will stay running. To stop it: vers stop $VM_ID"
echo "To delete it: vers delete $VM_ID"
