##
## EPITECH PROJECT, 2025
## flow [WSL: Ubuntu]
## File description:
## serverWebsocket
##

import asyncio
import websockets

async def serverWebsocket():
    async def handler(websocket):
        try:
            async for message in websocket:
                print(f"Received message: {message}")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed: {e.code} - {e.reason}")

    server = await websockets.serve(
        handler,
        "localhost",
        8765,
        ping_interval=60,      # Ping toutes les 60 secondes
        ping_timeout=180,      # Attendre 180 secondes pour le pong
        close_timeout=1000,      # Timeout de fermeture
    )
    print("WebSocket server started on ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(serverWebsocket())