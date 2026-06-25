import asyncio
import websockets

async def test():
    try:
        ws = await websockets.connect("wss://chess-2-8k6w.onrender.com")
        print("Success")
    except Exception as e:
        print(f"Error: {repr(e)}")

asyncio.run(test())
