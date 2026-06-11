"""Quick chat test — writes result to file."""
import httpx, json, asyncio, sys

async def main():
    body = {"message": "MO流程的L2 PO是谁？", "session_id": None, "persona_slug": "default"}
    full = ""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", "http://localhost:8001/api/chat/stream", json=body) as resp:
                print(f"Status: {resp.status_code}", flush=True)
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                            if event["type"] == "token":
                                full += event["data"]
                            elif event["type"] == "error":
                                print(f"Error: {event['data']}", flush=True)
                        except Exception:
                            pass
    except Exception as e:
        print(f"Exception: {e}", flush=True)

    with open(r"d:\数字分身\chat_test_result.txt", "w", encoding="utf-8") as f:
        f.write(full)
    print(f"Done. Response: {len(full)} chars", flush=True)

asyncio.run(main())
