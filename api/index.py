import re
import pdfplumber
from flask import Flask, request, jsonify

app = Flask(__name__)

def extract_emails_and_categories(pdf_file):
    results = {
        'brokers': {'active': [], 'inactive': [], 'pending': [], 'rejected': []},
        'carriers': {'active': [], 'inactive': [], 'pending': [], 'rejected': []}
    }
    
    # Regex pattern to match standard emails
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            current_category = 'carriers'
            current_status = 'active'
            
            for line in lines:
                line_upper = line.upper()
                
                # Category Detection
                if "BROKER" in line_upper:
                    current_category = 'brokers'
                elif "CARRIER" in line_upper or "FREIGHT FORWARDER" in line_upper:
                    current_category = 'carriers'
                
                # Status Detection
                if "INACTIVE" in line_upper or "REVOKED" in line_upper or "DISMISSED" in line_upper:
                    current_status = 'inactive'
                elif "PENDING" in line_upper:
                    current_status = 'pending'
                elif "REJECTED" in line_upper or "DENIED" in line_upper:
                    current_status = 'rejected'
                elif "ACTIVE" in line_upper or "GRANTED" in line_upper:
                    current_status = 'active'
                
                # Extract Emails from line
                found_emails = email_pattern.findall(line)
                for email in found_emails:
                    clean_email = email.strip().lower()
                    # Filter out useless files/extensions that match email patterns
                    if not clean_email.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.gif')):
                        results[current_category][current_status].append(clean_email)

    # Remove Duplicates
    for cat in results:
        for st in results[cat]:
            results[cat][st] = sorted(list(set(results[cat][st])))
            
    return results

@app.route('/api/process-pdf', methods=['POST'])
def process_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['file']
    try:
        results = extract_emails_and_categories(file)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def handler(request, start_response):
    return app(request, start_response)
