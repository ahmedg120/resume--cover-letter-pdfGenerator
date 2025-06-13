from flask import Flask, request, send_file, jsonify
import pdfx
import re
import os
import tempfile
import json
import subprocess
from groq import Groq
from werkzeug.utils import secure_filename
import io
import requests

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

client = Groq(api_key="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")  # Replace with your real key

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_pdf_text(pdf_path):
    pdf = pdfx.PDFx(pdf_path)
    text = pdf.get_text()
    urls = pdf.get_references_as_dict().get("url", [])
    return text + "\n\nExtracted URLs:\n" + "\n".join(urls)

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    return text.strip()

@app.route('/resume-to-pdf', methods=['POST'])
def resume_to_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    try:
        # Step 1: Save uploaded PDF
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)

        # Step 2: Extract and clean text
        raw_text = read_pdf_text(pdf_path)
        resume_text = clean_text(raw_text)

        # Step 3: Generate JSONResume via Groq
        prompt = f"""
You are an expert resume parser and formatter.

I will provide you with the raw text from a resume. Your task is to parse the content and generate a complete JSON in the format required by the jsonresume-theme-stackoverflow theme.

Use this schema as a base:

{{
  "basics": {{
    "name": "",
    "label": "",
    "image": "",
    "email": "",
    "phone": "",
    "url": "",
    "summary": "",
    "location": {{
      "address": "",
      "postalCode": "",
      "city": "",
      "countryCode": "",
      "region": ""
    }},
    "profiles": [
      {{
        "network": "",
        "username": "",
        "url": ""
      }}
    ]
  }},
  "work": [
    {{
      "name": "",
      "position": "",
      "url": "",
      "startDate": "",
      "endDate": "",
      "summary": "",
      "highlights": [""]
    }}
  ],
  "volunteer": [],
  "education": [
    {{
      "institution": "",
      "url": "",
      "area": "",
      "studyType": "",
      "startDate": "",
      "endDate": "",
      "score": "",
      "courses": [""]
    }}
  ],
  "awards": [],
  "certificates": [],
  "publications": [],
  "skills": [
    {{
      "name": "",
      "level": "",
      "keywords": [""]
    }}
  ],
  "languages": [],
  "interests": [],
  "references": []
}}

Instructions:
- Fill in this structure using only the information you extract from the resume text.
- If information is missing, leave fields blank or omit them.
- Make sure to include a well-written, professional 'summary' based on what you learn from the resume.

Resume text:
{resume_text}
"""
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        json_resume = json.loads(response.choices[0].message.content)

        # Step 4: Generate PDF with `npx resume export`
        tempdir = tempfile.mkdtemp()
        try:
            resume_json_path = os.path.join(tempdir, "resume.json")
            with open(resume_json_path, "w") as f:
                json.dump(json_resume, f, indent=2)

            output_pdf_path = os.path.join(tempdir, "resume.pdf")

            # Run the resume export command
            subprocess.run([
                "C:\\Program Files\\nodejs\\npx.cmd", "resume", "export", output_pdf_path,
                "--resume", resume_json_path,
                "--theme", "jsonresume-theme-stackoverflow"
            ], check=True)

            # Upload to Gofile.io
            try:
                # Upload directly to store1 server
                with open(output_pdf_path, 'rb') as file:
                    upload_response = requests.post(
                        'https://store1.gofile.io/uploadFile',
                        files={'file': file}
                    )
                    print("Gofile Response Status:", upload_response.status_code)  # Debug print
                    print("Gofile Response Text:", upload_response.text)  # Debug print
                    
                    if upload_response.status_code == 200:
                        response_json = upload_response.json()
                        if response_json.get('status') == 'ok':
                            pdf_url = response_json['data']['downloadPage']
                        else:
                            raise Exception(f"Upload failed: {response_json.get('status')}")
                    else:
                        raise Exception(f"Upload failed with status {upload_response.status_code}: {upload_response.text}")
            except Exception as e:
                print("Upload Error:", str(e))  # Debug print
                raise Exception(f"Failed to upload to Gofile: {str(e)}")

            # Clean up temporary files
            try:
                os.remove(resume_json_path)
                os.remove(output_pdf_path)
                os.rmdir(tempdir)
            except Exception as e:
                print(f"Warning: Failed to clean up temporary files: {e}")

            # Return the URL instead of the file
            return jsonify({
                "success": True,
                "pdf_url": pdf_url
            })

        except Exception as e:
            # Clean up on error
            try:
                if os.path.exists(resume_json_path):
                    os.remove(resume_json_path)
                if os.path.exists(output_pdf_path):
                    os.remove(output_pdf_path)
                os.rmdir(tempdir)
            except:
                pass
            raise e

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Resume export failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
