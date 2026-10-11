import os
import time
import requests

base = 'http://127.0.0.1:8000'
username = f'medtest_{int(time.time())}'
password = 'TestPass123!'
pdf_path = r'C:\Users\hi\Desktop\MediRAG AI\sample_medical_report.pdf'


def write_minimal_pdf(path):
    text = (
        'BT\n'
        '/F1 18 Tf\n'
        '50 750 Td\n'
        '(MediRAG AI Sample Medical Report) Tj\n'
        '0 -30 Td\n'
        '(Patient name: Emma Roy) Tj\n'
        '0 -30 Td\n'
        '(Age: 42) Tj\n'
        '0 -30 Td\n'
        '(Diagnosis: Type 2 diabetes mellitus) Tj\n'
        '0 -30 Td\n'
        '(Medication: Metformin 500 mg twice daily) Tj\n'
        '0 -30 Td\n'
        '(Blood pressure: 128/82 mmHg) Tj\n'
        '0 -30 Td\n'
        '(Temperature: 98.6 F) Tj\n'
        '0 -30 Td\n'
        '(HbA1c: 6.8%) Tj\n'
        '0 -40 Td\n'
        '(Follow-up advice: Continue medication and repeat HbA1c in three months.) Tj\n'
        'ET'
    )
    stream = text.encode('latin-1', 'replace')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        f'<< /Length {len(stream)} >>\nstream\n'.encode('latin-1') + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    pdf = b'%PDF-1.4\n'
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += f'{len(offsets)-1} 0 obj\n'.encode('latin-1') + obj + b'\nendobj\n'
    xref_start = len(pdf)
    pdf += f'xref\n0 {len(objects)+1}\n'.encode('latin-1')
    pdf += b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        pdf += f'{offset:010d} 00000 n \n'.encode('latin-1')
    pdf += f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n'.encode('latin-1')
    with open(path, 'wb') as fh:
        fh.write(pdf)


write_minimal_pdf(pdf_path)

register = requests.post(
    f'{base}/api/v1/auth/register',
    json={'full_name': 'QA Tester', 'username': username, 'password': password},
    timeout=60,
)
print('REGISTER', register.status_code)
print(register.text)
if register.status_code != 200:
    raise SystemExit(1)

token = register.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

with open(pdf_path, 'rb') as fh:
    upload = requests.post(
        f'{base}/api/v1/documents/upload',
        files={'file': ('sample_medical_report.pdf', fh, 'application/pdf')},
        headers=headers,
        timeout=180,
    )
print('UPLOAD', upload.status_code)
print(upload.text)
if upload.status_code != 200:
    raise SystemExit(1)

status = 'processing'
for _ in range(60):
    docs = requests.get(f'{base}/api/v1/documents/', headers=headers, timeout=30)
    doc = next((d for d in docs.json() if 'sample_medical_report' in d.get('filename', '')), None)
    if doc:
        status = doc.get('status', 'processing')
        print('DOC STATUS', status, doc)
        if status in ('completed', 'failed'):
            break
    time.sleep(3)
print('FINAL STATUS', status)
if status != 'completed':
    raise SystemExit(f'Expected completed status, got {status}')

query = requests.post(
    f'{base}/api/v1/chat/query',
    json={'query': 'What is the patient name?'},
    headers=headers,
    timeout=180,
)
print('QUERY', query.status_code)
print(query.text)
if query.status_code != 200:
    raise SystemExit(1)

if os.path.exists(pdf_path):
    os.remove(pdf_path)
