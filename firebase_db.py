import aiohttp
import asyncio
import json
import time
import copy
from debug_utils import check_invariants, log_minimal_snapshot
from chess_logic import serialize_state, deserialize_state, make_state

# Config from firebase-applet-config.json
PROJECT_ID = "gen-lang-client-0345401514"
DB_ID = "ai-studio-hiddenchessv153-f7c7ea56-b4b2-4926-bf9e-510c8f28287f"
API_KEY = "AIzaSyD_9JQVzd_AQSP9r8y1zr5hoQjLMGA8VuI"

BASE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/{DB_ID}/documents/rooms"

class FirebaseClient:
    def __init__(self):
        self.room_code = None
        self.color = None
        self.token = None
        self.polling = False
        self.poll_task = None
        self.on_state_update = None
        self.on_error = None
        self.last_update_time = None
        
    async def _poll(self):
        async with aiohttp.ClientSession() as session:
            while self.polling:
                if not self.room_code:
                    await asyncio.sleep(1)
                    continue
                    
                url = f"{BASE_URL}/{self.room_code}?key={API_KEY}"
                try:
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            update_time = data.get("updateTime")
                            if update_time != self.last_update_time:
                                self.last_update_time = update_time
                                fields = data.get("fields", {})
                                if "state" in fields:
                                    state_str = fields["state"].get("stringValue")
                                    if state_str:
                                        try:
                                            if self.on_state_update:
                                                self.on_state_update(state_str)
                                        except Exception as e:
                                            print("Error in callback:", e)
                except Exception as e:
                    print("Polling error:", e)
                    
                await asyncio.sleep(1.0)
            
    def start_polling(self, on_state_update, on_error=None):
        self.on_state_update = on_state_update
        self.on_error = on_error
        self.polling = True
        self.poll_task = asyncio.create_task(self._poll())
        
    def stop_polling(self):
        self.polling = False
        if self.poll_task:
            self.poll_task.cancel()
        
    async def create_room(self, room_code, token, initial_state_json):
        url = f"{BASE_URL}?documentId={room_code}&key={API_KEY}"
        doc = {
            "fields": {
                "state": {"stringValue": initial_state_json},
                "tokens": {
                    "mapValue": {
                        "fields": {
                            "w": {"stringValue": token}
                        }
                    }
                }
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=doc) as resp:
                return resp.status == 200

    async def join_room(self, room_code, token):
        url = f"{BASE_URL}/{room_code}?key={API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False, "Sala não encontrada"
                    
                data = await resp.json()
                fields = data.get("fields", {})
                tokens = fields.get("tokens", {}).get("mapValue", {}).get("fields", {})
                
                if "b" not in tokens:
                    # We can join as black
                    tokens["b"] = {"stringValue": token}
                    
                    # Update opponent_joined inside state
                    state_str = fields.get("state", {}).get("stringValue", "{}")
                    try:
                        state_dict = json.loads(state_str)
                        state_dict["opponent_joined"] = True
                        fields["state"] = {"stringValue": json.dumps(state_dict)}
                    except Exception:
                        pass
        
                    # Update the doc
                    doc = {
                        "fields": {
                            "state": fields.get("state"),
                            "tokens": {"mapValue": {"fields": tokens}}
                        }
                    }
                    async with session.patch(url, json=doc) as patch_resp:
                        if patch_resp.status == 200:
                            return True, {"color": "b"}
                    return False, "Erro ao entrar na sala"
                else:
                    if tokens.get("w", {}).get("stringValue") == token:
                        return True, {"color": "w", "reconnected": True}
                    if tokens.get("b", {}).get("stringValue") == token:
                        return True, {"color": "b", "reconnected": True}
                    return False, "Sala cheia"
            
    async def update_state(self, room_code, state_json, token, color):
        # We need to preserve the tokens field when patching
        url = f"{BASE_URL}/{room_code}?updateMask.fieldPaths=state&key={API_KEY}"
        doc = {
            "name": f"projects/{PROJECT_ID}/databases/{DB_ID}/documents/rooms/{room_code}",
            "fields": {
                "state": {"stringValue": state_json}
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=doc) as resp:
                return resp.status == 200

    def leave_room(self, room_code):
        # We could delete the room if empty, or just leave it
        pass

firebase_client = FirebaseClient()
