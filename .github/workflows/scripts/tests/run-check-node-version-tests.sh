#!/usr/bin/env bash
# Unit tests for check-node-version.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/check-node-version.sh"

TEST_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP_DIR"' EXIT

# Test 1: Node missing (filter out directory containing node from PATH)
NODE_PATH_DIR="$(dirname "$(command -v node || echo '/usr/bin/node')")"
PATH_WITHOUT_NODE=$(echo "$PATH" | tr ':' '\n' | grep -v -F "$NODE_PATH_DIR" | tr '\n' ':' | sed 's/:$//')

OUTPUT=$(PATH="$PATH_WITHOUT_NODE" bash "$CHECK_SCRIPT" 18 2>&1 || true)
if ! echo "$OUTPUT" | grep -q "Node.js is not installed"; then
  echo "FAIL: Expected error when node is missing, got: $OUTPUT"
  exit 1
fi
echo "OK   check-node-version.sh detects missing Node.js"

# Test 2: Invalid node version output
MOCK_NODE_INVALID_DIR="$TEST_TMP_DIR/bin_invalid"
mkdir -p "$MOCK_NODE_INVALID_DIR"
cat <<'MOCK_EOF' > "$MOCK_NODE_INVALID_DIR/node"
#!/usr/bin/env bash
echo "invalid-version-string"
MOCK_EOF
chmod +x "$MOCK_NODE_INVALID_DIR/node"

OUTPUT=$(PATH="$MOCK_NODE_INVALID_DIR:$PATH" bash "$CHECK_SCRIPT" 18 2>&1 || true)
if ! echo "$OUTPUT" | grep -q "Failed to parse Node.js version output"; then
  echo "FAIL: Expected parse error for invalid node version, got: $OUTPUT"
  exit 1
fi
echo "OK   check-node-version.sh handles invalid Node.js version output safely"

# Test 3: Insufficient node version
MOCK_NODE_OLD_DIR="$TEST_TMP_DIR/bin_old"
mkdir -p "$MOCK_NODE_OLD_DIR"
cat <<'MOCK_EOF' > "$MOCK_NODE_OLD_DIR/node"
#!/usr/bin/env bash
echo "v16.20.0"
MOCK_EOF
chmod +x "$MOCK_NODE_OLD_DIR/node"

OUTPUT=$(PATH="$MOCK_NODE_OLD_DIR:$PATH" bash "$CHECK_SCRIPT" 18 2>&1 || true)
if ! echo "$OUTPUT" | grep -q "is insufficient"; then
  echo "FAIL: Expected insufficient version error, got: $OUTPUT"
  exit 1
fi
echo "OK   check-node-version.sh detects insufficient Node.js version"

# Test 4: Sufficient node version
MOCK_NODE_OK_DIR="$TEST_TMP_DIR/bin_ok"
mkdir -p "$MOCK_NODE_OK_DIR"
cat <<'MOCK_EOF' > "$MOCK_NODE_OK_DIR/node"
#!/usr/bin/env bash
echo "v20.11.0"
MOCK_EOF
chmod +x "$MOCK_NODE_OK_DIR/node"

OUTPUT=$(PATH="$MOCK_NODE_OK_DIR:$PATH" bash "$CHECK_SCRIPT" 18 2>&1)
echo "OK   check-node-version.sh passes for sufficient Node.js version"

echo "All check-node-version test cases passed."
