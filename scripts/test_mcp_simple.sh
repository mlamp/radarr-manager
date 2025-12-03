#!/bin/bash
# Simple test of MCP SSE server

echo "=== Step 1: Open SSE connection ==="
curl -N -H "Accept: text/event-stream" "http://localhost:8091/mcp/sse" 2>&1 | while IFS= read -r line; do
    echo "$line"

    # Extract session ID from endpoint event
    if [[ "$line" =~ session_id=([a-f0-9]+) ]]; then
        SESSION_ID="${BASH_REMATCH[1]}"
        echo ""
        echo "=== Extracted Session ID: $SESSION_ID ==="
        echo ""

        # In a subshell, send initialize request
        (
            sleep 1
            echo "=== Step 2: Send initialize request ==="
            curl -X POST "http://localhost:8091/mcp/messages?session_id=$SESSION_ID" \
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
                }'
            echo ""

            sleep 2
            echo "=== Step 3: Send search_movie tool call ==="
            curl -X POST "http://localhost:8091/mcp/messages?session_id=$SESSION_ID" \
                -H "Content-Type: application/json" \
                -d '{
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "search_movie",
                        "arguments": {"title": "The Matrix", "year": 1999}
                    }
                }'
            echo ""

            # Kill the SSE curl after 5 seconds
            sleep 5
            pkill -P $$ curl
        ) &
    fi

    # Stop after 10 seconds total
    if [[ $(date +%s) -gt $(($(date +%s) + 10)) ]]; then
        break
    fi
done

echo ""
echo "=== Test complete ==="
