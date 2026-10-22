"""
=============================================================================
SCRIPT: backend/scripts/deploy_indexes.py
MÔ TẢ:
    Tự động đọc cấu hình firestore.indexes.json và tạo các Composite Index
    trên Google Cloud Firestore thông qua Cloud Firestore Admin REST API
    sử dụng Service Account credentials của dự án.
=============================================================================
"""

import json
import os
import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

# Dynamic configuration from app settings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_FILE = os.path.join(os.path.dirname(BASE_DIR), "firestore.indexes.json")

def get_credentials_path() -> str:
    from app.core.config import get_settings
    return get_settings().FIREBASE_CREDENTIALS_PATH

def main():
    print("=" * 60)
    print(" BẮT ĐẦU TẠO COMPOSITE INDEXES CHO CLOUD FIRESTORE")
    print("=" * 60)

    cred_path = get_credentials_path()
    if not os.path.exists(cred_path):
        print(f"[ERROR] Không tìm thấy credentials tại: {cred_path}")
        return

    if not os.path.exists(INDEX_FILE):
        print(f"[ERROR] Không tìm thấy file index tại: {INDEX_FILE}")
        return

    with open(cred_path, "r", encoding="utf-8") as f:
        cred_info = json.load(f)
    project_id = cred_info.get("project_id", "guardian-ai-flatform")

    # Xác thực OAuth2 qua Service Account
    credentials = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/datastore",
        ],
    )
    credentials.refresh(Request())
    token = credentials.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    indexes = config.get("indexes", [])
    print(f"Project: {project_id}")
    print(f"Tổng số index cần tạo: {len(indexes)}\n")

    for i, idx in enumerate(indexes, 1):
        col = idx["collectionGroup"]
        query_scope = idx.get("queryScope", "COLLECTION")
        fields = idx["fields"]

        url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/collectionGroups/{col}/indexes"
        body = {
            "queryScope": query_scope,
            "fields": fields,
        }

        field_summary = " + ".join([f"{f['fieldPath']} ({f['order']})" for f in fields])
        print(f"[{i}/{len(indexes)}] Collection: '{col}' | Fields: {field_summary}")

        res = requests.post(url, headers=headers, json=body)
        if res.status_code == 200:
            print("   -> [THÀNH CÔNG] Đã gửi lệnh tạo index lên Google Cloud (State: CREATING/READY).\n")
        elif res.status_code == 409:
            print("   -> [ĐÃ TỒN TẠI] Index này đã được tạo trước đó trên Firestore.\n")
        else:
            print(f"   -> [LỖI {res.status_code}] {res.text}\n")

    print("=" * 60)
    print(" HOÀN TẤT QUY TRÌNH TẠO COMPOSITE INDEXES!")
    print("=" * 60)

if __name__ == "__main__":
    main()
