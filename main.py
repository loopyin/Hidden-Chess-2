import asyncio
import client

# Main application entry point
# Harmless change requested by user
if __name__ == '__main__':
    print("Initializing HiChess...")
    asyncio.run(client.game_loop())
