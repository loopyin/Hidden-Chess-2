import asyncio
import websockets

async def test():
    try:
        ws = await websockets.connect("wss://hidden-chess-lnbg.onrender.com")
        print("Success")
    except Exception as e:
        print(f"Error: {repr(e)}")

asyncio.run(test())
