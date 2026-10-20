"""
Modulo de persistencia desacoplado para MindMapGenerator.
Soporta MongoDB si esta disponible, con fallback automatico a almacenamiento
local en ficheros JSON en el directorio 'data/'.
"""

import os
import json
import datetime
from typing import Optional, Dict, Any, List

class LocalJSONStorage:
    def __init__(self, base_dir: str):
        self.base_dir = os.path.join(base_dir, "data")
        self.maps_dir = os.path.join(self.base_dir, "maps")
        self.lists_dir = os.path.join(self.base_dir, "lists")
        os.makedirs(self.maps_dir, exist_ok=True)
        os.makedirs(self.lists_dir, exist_ok=True)

    def _json_serial(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    def save_list(self, list_doc: Dict[str, Any]):
        file_path = os.path.join(self.lists_dir, f"{list_doc['id']}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(list_doc, f, default=self._json_serial, indent=2, ensure_ascii=False)

    def save_map(self, map_doc: Dict[str, Any]):
        file_path = os.path.join(self.maps_dir, f"{map_doc['id']}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(map_doc, f, default=self._json_serial, indent=2, ensure_ascii=False)

    def get_list(self, list_id: str) -> Optional[Dict[str, Any]]:
        file_path = os.path.join(self.lists_dir, f"{list_id}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def get_map(self, map_id: str) -> Optional[Dict[str, Any]]:
        file_path = os.path.join(self.maps_dir, f"{map_id}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def get_maps_by_list(self, list_id: str) -> List[Dict[str, Any]]:
        results = []
        for f in os.listdir(self.maps_dir):
            if f.endswith(".json"):
                fp = os.path.join(self.maps_dir, f)
                try:
                    with open(fp, "r", encoding="utf-8") as file:
                        doc = json.load(file)
                        if doc.get("idList") == list_id and not doc.get("delete", False):
                            results.append(doc)
                except Exception:
                    pass
        results.sort(key=lambda x: x.get("date", ""), reverse=True)
        return results

    def get_user_lists(self, user_id: str) -> List[Dict[str, Any]]:
        results = []
        for f in os.listdir(self.lists_dir):
            if f.endswith(".json"):
                fp = os.path.join(self.lists_dir, f)
                try:
                    with open(fp, "r", encoding="utf-8") as file:
                        doc = json.load(file)
                        if (doc.get("idUser") == user_id or doc.get("idUser") == "all") and not doc.get("delete", False):
                            results.append(doc)
                except Exception:
                    pass
        results.sort(key=lambda x: x.get("date", ""), reverse=True)
        return results

    def delete_list(self, list_id: str, user_id: str) -> bool:
        doc = self.get_list(list_id)
        if doc:
            doc["delete"] = True
            self.save_list(doc)
            return True
        return False

    def delete_map(self, map_id: str, user_id: str) -> bool:
        doc = self.get_map(map_id)
        if doc:
            doc["delete"] = True
            self.save_map(doc)
            return True
        return False


class MongoStorage:
    def __init__(self, mongo_uri: str, db_name: str = "maps"):
        from pymongo import MongoClient
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        # Test connection
        self.client.admin.command('ping')
        self.db = self.client[db_name]
        self.MapasColeccion = self.db["map"]
        self.ListasColeccion = self.db["list"]

    def save_list(self, list_doc: Dict[str, Any]):
        self.ListasColeccion.update_one({"id": list_doc["id"]}, {"$set": list_doc}, upsert=True)

    def save_map(self, map_doc: Dict[str, Any]):
        self.MapasColeccion.update_one({"id": map_doc["id"]}, {"$set": map_doc}, upsert=True)

    def get_list(self, list_id: str) -> Optional[Dict[str, Any]]:
        return self.ListasColeccion.find_one({"id": list_id})

    def get_map(self, map_id: str) -> Optional[Dict[str, Any]]:
        return self.MapasColeccion.find_one({"id": map_id})

    def get_maps_by_list(self, list_id: str) -> List[Dict[str, Any]]:
        cursor = self.MapasColeccion.find({"idList": list_id, "delete": False}).sort("date", -1)
        return list(cursor)

    def get_user_lists(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.ListasColeccion.find({"idUser": user_id, "delete": False}).sort("date", -1)
        return list(cursor)

    def delete_list(self, list_id: str, user_id: str) -> bool:
        res = self.ListasColeccion.update_one({"id": list_id, "idUser": user_id}, {"$set": {"delete": True}})
        return res.modified_count > 0

    def delete_map(self, map_id: str, user_id: str) -> bool:
        res = self.MapasColeccion.update_one({"id": map_id, "idUser": user_id}, {"$set": {"delete": True}})
        return res.modified_count > 0


def init_storage(base_dir: str, mongo_uri: Optional[str] = None, db_name: str = "maps"):
    """
    Inicializa el motor de persistencia. Intenta conectar a MongoDB si se define URI.
    Si falla o no se define, activa el almacenamiento local en JSON.
    """
    if mongo_uri:
        try:
            storage = MongoStorage(mongo_uri, db_name)
            print("[Storage] Conectado exitosamente a MongoDB:", mongo_uri)
            return storage
        except Exception as e:
            print(f"[Storage] No se pudo conectar a MongoDB ({e}). Activando fallback local en JSON.")
    
    storage = LocalJSONStorage(base_dir)
    print(f"[Storage] Almacenamiento local JSON activo en: {os.path.join(base_dir, 'data')}")
    return storage
