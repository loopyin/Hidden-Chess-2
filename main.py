import asyncio
import client

if __name__ == '__main__':
    print("Initializing Hidden Chess...")
    asyncio.run(client.game_loop())
