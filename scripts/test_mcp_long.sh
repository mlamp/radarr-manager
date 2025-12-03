#!/bin/bash
# Test MCP SSE with long-lived connection

echo "=== Opening SSE connection (will stay open for 30 seconds) ==="

# Start SSE connection and save output
curl -N -H "Accept: text/event-stream" "http://localhost:8091/mcp/sse" 2>&1 | while IFS= read -r line; do
    echo "[SSE] $line"

    # Extract session ID
    if [[ "$line" =~ session_id=([a-f0-9]+) ]]; then
        SESSION_ID="${BASH_REMATCH[1]}"
        echo ""
        echo "=== Session ID: $SESSION_ID ==="
        echo ""

        # Send requests in background
        (
            sleep 1
            echo "=== [1s] Sending initialize request ==="
            curl -s -X POST "http://localhost:8091/mcp/messages?session_id=$SESSION_ID" \
                -H "Content-Type: application/json" \
                -d '{
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0"}
                    }
                }' | jq -c '.'
            echo ""

            sleep 3
            echo "=== [4s] Sending search_movie tool call ==="
            curl -s -X POST "http://localhost:8091/mcp/messages?session_id=$SESSION_ID" \
                -H "Content-Type: application/json" \
                -d '{
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "search_movie",
                        "arguments": {"title": "The Matrix", "year": 1999}
                    }
                }' | jq -c '.'
            echo ""

            echo "=== Waiting 10 seconds for response... ==="
            sleep 10

            echo "=== [14s] Closing connection ==="
            pkill -P $$ curl 2>/dev/null
        ) &
    fi
done

echo ""
echo "=== Test complete ==="
