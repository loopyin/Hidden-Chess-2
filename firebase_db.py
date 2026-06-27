import urllib.request
import urllib.error
import asyncio
import json
import time
import copy
import threading
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
        self.thread = None
        self.on_state_update = None
        self.on_error = None
        self.last_update_time = None
        
    def _poll(self):
        while self.polling:
            if not self.room_code:
                time.sleep(1)
                continue
                
            url = f"{BASE_URL}/{self.room_code}?key={API_KEY}&_t={int(time.time() * 1000)}"
            try:
                req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode('utf-8'))
                        update_time = data.get("updateTime")
                        if update_time != self.last_update_time:
                            self.last_update_time = update_time
                            fields = data.get("fields", {})
                            if "state" in fields:
                                state_str = fields["state"].get("stringValue")
                                if state_str:
                                    try:
                                        tokens_fields = fields.get("tokens", {}).get("mapValue", {}).get("fields", {})
                                        if "b" in tokens_fields:
                                            state_dict = json.loads(state_str)
                                            if not state_dict.get("opponent_joined"):
                                                state_dict["opponent_joined"] = True
                                                state_str = json.dumps(state_dict)
                                    except Exception:
                                        pass
                                    try:
                                        if self.on_state_update:
                                            self.on_state_update(state_str)
                                    except Exception as e:
                                        print("Error in callback:", e)
            except Exception as e:
                pass
                
            time.sleep(1.0)
            
    def start_polling(self, on_state_update, on_error=None):
        self.on_state_update = on_state_update
        self.on_error = on_error
        self.polling = True
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()
        
    def stop_polling(self):
        self.polling = False
        
    async def create_room(self, room_code, token, initial_state_json):
        self.room_code = room_code
        self.token = token
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
        
        def _post():
            data = json.dumps(doc).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status == 200
            except Exception as e:
                print("create_room error:", e)
                return False
                
        return await asyncio.to_thread(_post)

    async def join_room(self, room_code, token):
        self.room_code = room_code
        self.token = token
        url = f"{BASE_URL}/{room_code}?key={API_KEY}"
        
        def _join():
            req = urllib.request.Request(url)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status != 200:
                        return False, "Sala não encontrada"
                    data = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                print("join_room fetch error:", e)
                return False, "Sala não encontrada"
                
            fields = data.get("fields", {})
            tokens = fields.get("tokens", {}).get("mapValue", {}).get("fields", {})
            
            if "b" not in tokens:
                tokens["b"] = {"stringValue": token}
                state_str = fields.get("state", {}).get("stringValue", "{}")
                try:
                    state_dict = json.loads(state_str)
                    state_dict["opponent_joined"] = True
                    fields["state"] = {"stringValue": json.dumps(state_dict)}
                except Exception:
                    pass
    
                doc = {
                    "fields": {
                        "state": fields.get("state"),
                        "tokens": {"mapValue": {"fields": tokens}}
                    }
                }
                
                data_encoded = json.dumps(doc).encode('utf-8')
                patch_url = f"{BASE_URL}/{room_code}?updateMask.fieldPaths=state&updateMask.fieldPaths=tokens&key={API_KEY}"
                patch_req = urllib.request.Request(patch_url, data=data_encoded, headers={'Content-Type': 'application/json'}, method='PATCH')
                try:
                    with urllib.request.urlopen(patch_req, timeout=10) as patch_resp:
                        if patch_resp.status == 200:
                            return True, {"color": "b"}
                except Exception as e:
                    print("join_room patch error:", e)
                return False, "Erro ao entrar na sala"
            else:
                if tokens.get("w", {}).get("stringValue") == token:
                    return True, {"color": "w", "reconnected": True}
                if tokens.get("b", {}).get("stringValue") == token:
                    state_str = fields.get("state", {}).get("stringValue", "{}")
                    try:
                        state_dict = json.loads(state_str)
                        if not state_dict.get("opponent_joined"):
                            state_dict["opponent_joined"] = True
                            fields["state"] = {"stringValue": json.dumps(state_dict)}
                            
                            doc = {
                                "fields": {
                                    "state": fields.get("state"),
                                    "tokens": {"mapValue": {"fields": tokens}}
                                }
                            }
                            data_encoded = json.dumps(doc).encode('utf-8')
                            patch_url = f"{BASE_URL}/{room_code}?updateMask.fieldPaths=state&updateMask.fieldPaths=tokens&key={API_KEY}"
                            patch_req = urllib.request.Request(patch_url, data=data_encoded, headers={'Content-Type': 'application/json'}, method='PATCH')
                            with urllib.request.urlopen(patch_req, timeout=10) as patch_resp:
                                pass
                    except Exception as e:
                        print("join_room reconnect patch error:", e)
                    return True, {"color": "b", "reconnected": True}
                return False, "Sala cheia"
                
        return await asyncio.to_thread(_join)
            
    async def update_state(self, room_code, state_json, token, color):
        url = f"{BASE_URL}/{room_code}?updateMask.fieldPaths=state&key={API_KEY}"
        doc = {
            "name": f"projects/{PROJECT_ID}/databases/{DB_ID}/documents/rooms/{room_code}",
            "fields": {
                "state": {"stringValue": state_json}
            }
        }
        
        def _patch():
            data = json.dumps(doc).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='PATCH')
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status == 200
            except Exception as e:
                print("update_state error:", e)
                return False
                
        return await asyncio.to_thread(_patch)

    def leave_room(self, room_code):
        pass

firebase_client = FirebaseClient()
