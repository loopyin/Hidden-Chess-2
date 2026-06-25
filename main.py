import asyncio
import client

if __name__ == '__main__':
    print("Initializing Shadow Chess...")
    asyncio.run(client.game_loop())
