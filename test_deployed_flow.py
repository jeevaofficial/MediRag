import requests
import time
import os
import uuid

API_BASE = "https://medirag-798u.onrender.com/api/v1"
username = f"testuser_{uuid.uuid4().hex[:6]}"
password = "TestPassword123!"

print("1. Registering user...")
res = requests.post(f"{API_BASE}/auth/register", json={
    "full_name": "Test User",
    "username": username,
    "password": password
})
print("Register:", res.status_code, res.text)

print("\n2. Logging in...")
res = requests.post(f"{API_BASE}/auth/login", data={
    "username": username,
    "password": password
})
print("Login:", res.status_code)
token = res.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

print("\n3. Creating dummy PDF...")
with open("test_medical.pdf", "wb") as f:
    # Just a small dummy PDF content
    f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 53 >>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Patient has a fever of 102F) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000204 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n306\n%%EOF\n")

print("\n4. Uploading PDF...")
with open("test_medical.pdf", "rb") as f:
    res = requests.post(f"{API_BASE}/documents/upload", headers=headers, files={"file": ("test_medical.pdf", f, "application/pdf")})
print("Upload:", res.status_code, res.text)
doc_id = res.json().get("id")

print("\n5. Waiting for indexing...")
while True:
    time.sleep(3)
    res = requests.get(f"{API_BASE}/documents/", headers=headers)
    docs = res.json()
    if not docs:
        print("Document missing!")
        break
    doc = docs[0]
    print(f"Status: {doc['status']}")
    if doc["status"] in ["indexed", "error"]:
        break

print("\n6. Querying RAG...")
res = requests.post(f"{API_BASE}/chat/query", headers=headers, json={"query": "What is the patient's fever?"})
print("Query:", res.status_code)
print(res.json())

print("\n7. Cleaning up...")
res = requests.delete(f"{API_BASE}/documents/{doc_id}", headers=headers)
print("Delete:", res.status_code, res.text)
os.remove("test_medical.pdf")
