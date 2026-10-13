import re
import requests
import pdfplumber
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

app = Flask(__name__)

def extract_mc_dot_from_pdf(pdf_file):
    records = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split('\n')
            current_category = "carriers"
            
            for line in lines:
                line_upper = line.upper()
                
                if "BROKER OF" in line_upper:
                    current_category = "brokers"
                elif "MOTOR CARRIER OF" in line_upper or "FREIGHT FORWARDER" in line_upper or "ENTERPRISE MOTOR" in line_upper:
                    current_category = "carriers"
                
                mc_match = re.search(r'\b(?:MC|FF|MX)[-\s]?(\d{5,8})\b', line, re.IGNORECASE)
                dot_match = re.search(r'\b(?:USDOT|DOT)?\s*#?\s*(\d{6,8})\b', line, re.IGNORECASE)
                
                if mc_match:
                    mc_num = mc_match.group(1).strip()
                    records.append({'type': current_category, 'id_type': 'MC', 'id_val': mc_num})
                elif dot_match:
                    dot_num = dot_match.group(1).strip()
                    if len(dot_num) >= 6:
                        records.append({'type': current_category, 'id_type': 'DOT', 'id_val': dot_num})
                        
    return records

def scrape_fmcsa_motus(id_type, id_val):
    """
    Motus / Safer FMCSA Snapshot Scraping Method
    """
    url = "https://safer.fmcsa.dot.gov/query.asp"
    
    payload = {
        'searchtype': 'ANY',
        'query_type': 'queryCarrierSnapshot',
        'query_param': 'MC_MX' if id_type == 'MC' else 'USDOT',
        'query_string': id_val
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://safer.fmcsa.dot.gov/CompanySnapshot.aspx'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=6)
        if response.status_code == 200:
            html_text = response.text
            soup = BeautifulSoup(html_text, 'html.parser')
            page_text = soup.get_text().upper()
            
            status = 'inactive'
            if 'RECORD INACTIVE' in page_text or 'NOT AUTHORIZED' in page_text:
                status = 'inactive'
            elif 'AUTHORIZED FOR' in page_text or 'ACTIVE' in page_text:
                status = 'active'
            elif 'PENDING' in page_text:
                status = 'pending'
            elif 'REJECTED' in page_text or 'DISMISSED' in page_text:
                status = 'rejected'

            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html_text)
            email = email_match.group(0).lower() if email_match else None
            
            return email, status
    except Exception:
        pass
        
    return None, None

@app.route('/api/process-pdf', methods=['POST'])
def process_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['file']
    records = extract_mc_dot_from_pdf(file)
    
    results = {
        'brokers': {'active': [], 'inactive': [], 'pending': [], 'rejected': []},
        'carriers': {'active': [], 'inactive': [], 'pending': [], 'rejected': []}
    }
    
    unique_records = [dict(t) for t in {tuple(d.items()) for d in records}]
    
    for rec in unique_records:
        email, status = scrape_fmcsa_motus(rec['id_type'], rec['id_val'])
        
        if email and status:
            category = rec['type']
            results[category][status].append(email)
            
    for cat in results:
        for st in results[cat]:
            results[cat][st] = sorted(list(set(results[cat][st])))
            
    return jsonify(results)

def handler(request, start_response):
    return app(request, start_response)
