"""Direct test of chat endpoint with verbose logging."""
import asyncio, json, httpx

async def main():
    body = {"message": "MO流程第二季度执行的总体业务效果如何？请详细回答。", "session_id": None, "persona_slug": "default"}
    full = ""
    token_count = 0
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", "http://localhost:8001/api/chat/stream", json=body) as resp:
            print(f"Status: {resp.status_code}")
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event["type"] == "token":
                            token_count += 1
                            full += event["data"]
                        elif event["type"] == "done":
                            print(f"[DONE] session={event['data'].get('session_id')}")
                        elif event["type"] == "error":
                            print(f"[ERROR] {event['data']}")
                    except Exception:
                        pass

    print(f"\nTokens received: {token_count}")
    print(f"Total chars: {len(full)}")
    print(f"Last 300 chars:\n{full[-300:]}")
    print(f"\n=== FULL RESPONSE ===")
    print(full)

asyncio.run(main())
