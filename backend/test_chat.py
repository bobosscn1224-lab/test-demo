"""Test chat streaming with RAG knowledge context."""
import httpx, json, asyncio

async def main():
    body = {"message": "MO流程的L2 PO是谁？", "session_id": None, "persona_slug": "default"}
    full = ""
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", "http://localhost:8001/api/chat/stream", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event["type"] == "token":
                            full += event["data"]
                        elif event["type"] == "done":
                            print(f"[Done: session={event['data'].get('session_id')}]")
                        elif event["type"] == "error":
                            print(f"[Error: {event['data']}]")
                    except Exception:
                        pass
    print("\n=== AI Response ===")
    print(full)

asyncio.run(main())
