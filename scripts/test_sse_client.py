#!/usr/bin/env python3
"""Test script to verify MCP SSE transport is working correctly."""

import asyncio
import json
import uuid
from typing import Any

import httpx


async def test_mcp_sse_connection():
    """Test MCP server SSE connection and tool calling."""
    base_url = "http://localhost:8091"
    session_id = str(uuid.uuid4().hex)

    print(f"Testing MCP SSE connection to {base_url}")
    print(f"Session ID: {session_id}\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Connect to SSE endpoint
        print("Step 1: Opening SSE connection...")
        async with client.stream("GET", f"{base_url}/mcp/sse") as response:
            print(f"SSE connection status: {response.status_code}")
            print(f"SSE headers: {dict(response.headers)}\n")

            if response.status_code != 200:
                print("❌ Failed to open SSE connection")
                return

            # Step 2: Send initialize request
            print("Step 2: Sending initialize request...")
            init_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0",
                    },
                },
            }

            post_response = await client.post(
                f"{base_url}/mcp/messages",
                params={"session_id": session_id},
                json=init_message,
            )
            print(f"Initialize response status: {post_response.status_code}")
            print(f"Initialize response: {post_response.text}\n")

            # Step 3: Read SSE events
            print("Step 3: Reading SSE events...")
            event_count = 0
            async for line in response.aiter_lines():
                if not line:
                    continue

                print(f"SSE line: {line}")
                event_count += 1

                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    try:
                        event_data = json.loads(data)
                        print(f"Parsed event: {json.dumps(event_data, indent=2)}\n")

                        # If we got initialize response, send tool call
                        if event_data.get("id") == 1:
                            print("Step 4: Sending search_movie tool call...")
                            tool_call = {
                                "jsonrpc": "2.0",
                                "id": 2,
                                "method": "tools/call",
                                "params": {
                                    "name": "search_movie",
                                    "arguments": {
                                        "title": "The Matrix",
                                        "year": 1999,
                                    },
                                },
                            }

                            post_response = await client.post(
                                f"{base_url}/mcp/messages",
                                params={"session_id": session_id},
                                json=tool_call,
                            )
                            print(f"Tool call response status: {post_response.status_code}")
                            print(f"Tool call response: {post_response.text}\n")

                        # If we got tool response, we're done
                        if event_data.get("id") == 2:
                            print("✅ Successfully received tool response!")
                            return

                    except json.JSONDecodeError as e:
                        print(f"❌ Failed to parse JSON: {e}")
                        print(f"Raw data: {data}\n")

                # Stop after 10 events to avoid infinite loop
                if event_count > 10:
                    print("⚠️  Stopping after 10 events")
                    break


if __name__ == "__main__":
    asyncio.run(test_mcp_sse_connection())
