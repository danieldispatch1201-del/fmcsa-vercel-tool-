import re
import pdfplumber
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

def extract_data_from_pdf(pdf_file):
    extracted_records = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split('\n')
            current_category = "Carrier"
            for line in lines:
                if "BROKER OF" in line.upper():
                    current_category = "Broker"
                elif "MOTOR CARRIER OF" in line.upper() or "FREIGHT FORWARDER" in line.upper():
                    current_category = "Carrier"
                
                # USDOT یا MC نمبر نکالنا
                dot_match = re.search(r'(?:USDOT|MC|FF)\s*[-#]?\s*(\d+)', line, re.IGNORECASE)
                if dot_match:
                    num = dot_match.group(1)
                    extracted_records.append({
                        'type': current_category,
                        'id': num
                    })
    return extracted_records

def fetch_fmcsa_details(id_number):
    try:
        # FMCSA Public API Endpoint
        url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/{id_number}?webKey=c323f46f4eb27eb294e75cb70d65427d1a5bf068"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            carrier = data.get('content', {}).get('carrier', {})
            if carrier:
                email = carrier.get('emailAddress')
                allowed = carrier.get('allowedToOperate', 'N')
                
                if allowed == 'Y':
                    status = 'active'
                elif allowed == 'N':
                    status = 'inactive'
                elif 'P' in str(allowed):
                    status = 'pending'
                else:
                    status = 'rejected'
                    
                if email and "@" in email and email.lower() != "none":
                    return email.strip(), status
    except Exception:
        pass
    return None, None

@app.route('/api/process-pdf', methods=['POST'])
def process_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['file']
    records = extract_data_from_pdf(file)
    
    results = {
        'brokers': {'active': [], 'inactive': [], 'pending': [], 'rejected': []},
        'carriers': {'active': [], 'inactive': [], 'pending': [], 'rejected': []}
    }
    
    for record in records:
        email, status = fetch_fmcsa_details(record['id'])
        if email and status:
            category = 'brokers' if record['type'] == 'Broker' else 'carriers'
            results[category][status].append(email)
            
    # ڈوپلیکیٹ ختم کرنا
    for cat in results:
        for st in results[cat]:
            results[cat][st] = list(set(results[cat][st]))
            
    return jsonify(results)

# Vercel Serverless Entry Point
def handler(request, start_response):
    return app(request, start_response)
