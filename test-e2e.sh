#!/bin/bash
# End-to-end test script for Dispatch
# Usage: ./test-e2e.sh [port]
# Prerequisites: server running on the given port (default 8000)

set -euo pipefail

PORT=${1:-8000}
BASE="http://localhost:$PORT"
USER_ID="test-user-123"

echo "=== Dispatch E2E Test ==="
echo "Target: $BASE"
echo ""

# 1. Health check
echo "1. Health check..."
curl -sf "$BASE/" | python3 -m json.tool
echo ""

# 2. Create a project
echo "2. Creating project..."
PROJECT_RESP=$(curl -sf "$BASE/api/projects" \
  -H 'Content-Type: application/json' \
  -d "{\"user_id\": \"$USER_ID\", \"name\": \"e2e-test-project\", \"file_path\": \"/tmp/my-test-project\"}")
echo "$PROJECT_RESP" | python3 -m json.tool
PROJECT_ID=$(echo "$PROJECT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['project_id'])")
echo "   Project ID: $PROJECT_ID"
echo ""

# 3. List projects
echo "3. Listing projects..."
curl -sf "$BASE/api/projects/$USER_ID" | python3 -m json.tool
echo ""

# 4. Send a shell command via unified endpoint
echo "4. Sending unified command (shell: ls)..."
CMD_RESP=$(curl -sf "$BASE/api/unified/commands" \
  -H 'Content-Type: application/json' \
  -d "{\"project_id\": \"$PROJECT_ID\", \"prompt\": \"ls -la\", \"provider\": \"shell\"}")
echo "$CMD_RESP" | python3 -m json.tool
COMMAND_ID=$(echo "$CMD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_id'])")
echo "   Command ID: $COMMAND_ID"
echo ""

# 5. Check timeline
echo "5. Checking timeline..."
curl -sf "$BASE/api/unified/timeline" | python3 -m json.tool
echo ""

# 6. Dashboard
echo "6. Dashboard..."
curl -sf "$BASE/api/dashboard/$USER_ID" | python3 -m json.tool
echo ""

echo "=== Done ==="
echo ""
echo "Command $COMMAND_ID is queued. To execute it, start the local agent:"
echo ""
echo "  cd server && source .venv/bin/activate"
echo "  cd ../local-agent && python3 dispatch_local_agent.py \\"
echo "    --backend-url $BASE \\"
echo "    --project-path /tmp/my-test-project \\"
echo "    --project-id $PROJECT_ID \\"
echo "    --agent-token dummy"
echo ""
echo "Then re-check the timeline to see results:"
echo "  curl -s '$BASE/api/unified/timeline' | python3 -m json.tool"
