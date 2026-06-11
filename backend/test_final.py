"""Final E2E test after cleanup."""
import httpx, json, asyncio

BASE = "http://localhost:8001"

async def main():
    # Add correction for L2PO
    async with httpx.AsyncClient(timeout=60) as c:
        await c.post(f"{BASE}/api/knowledge/corrections", json={
            "question": "MO流程的L2PO是谁",
            "correct_answer": "根据M11.1验证商机流程说明文件V1.0，MO流程的L2 PO是曹曦，L3 PO是汪霏"
        })

    # Test chat
    body = {"message": "MO流程的L2PO是谁？", "session_id": None, "persona_slug": "default"}
    full = ""
    async with httpx.AsyncClient(timeout=60) as c:
        async with c.stream("POST", f"{BASE}/api/chat/stream", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        if ev["type"] == "token":
                            full += ev["data"]
                    except Exception:
                        pass
        print(f"A: {full[:400]}")
        print(f"Contains 曹曦: {'曹曦' in full}")
        print(f"Cites source: {'M11' in full or '验证商机' in full}")

        # Clean up
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        for corr in r.json()["corrections"]:
            await c.delete(f"{BASE}/api/knowledge/corrections/{corr['id']}")

asyncio.run(main())
