from flask import Flask, request, send_file, jsonify
import pdfx
import re
import os
import tempfile
import json
import subprocess
import shutil
import platform
from groq import Groq
from werkzeug.utils import secure_filename
import io

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
            print(f"Created temporary directory: {tempdir}")
            
            resume_json_path = os.path.join(tempdir, "resume.json")
            with open(resume_json_path, "w") as f:
                json.dump(json_resume, f, indent=2)
            print(f"Created JSON file at: {resume_json_path}")

            output_pdf_path = os.path.join(tempdir, "resume.pdf")
            print(f"Will save PDF to: {output_pdf_path}")

            # Change to the app directory where node_modules is located
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            print(f"Changed to directory: {os.getcwd()}")

            # Use npx directly
            npx_cmd = "npx"
            if platform.system() == "Windows":
                npx_cmd = "npx.cmd"

            print(f"Using npx command: {npx_cmd}")
            print(f"Directory contents: {os.listdir('.')}")
            print(f"node_modules exists: {os.path.exists('node_modules')}")

            # Run the resume-cli command
            result = subprocess.run([
                npx_cmd, "resume-cli", "export", output_pdf_path,
                "--resume", resume_json_path,
                "--theme", "jsonresume-theme-stackoverflow"
            ], capture_output=True, text=True, check=True)
            
            print(f"resume-cli output: {result.stdout}")
            print(f"resume-cli errors: {result.stderr}")

            # Check if the PDF was created
            if not os.path.exists(output_pdf_path):
                raise FileNotFoundError(f"PDF was not created at {output_pdf_path}")

            # Read the PDF file into memory
            with open(output_pdf_path, 'rb') as pdf_file:
                pdf_data = pdf_file.read()
            print(f"Successfully read PDF file, size: {len(pdf_data)} bytes")

            # Create a BytesIO object to send the PDF
            pdf_io = io.BytesIO(pdf_data)
            pdf_io.seek(0)

            return send_file(
                pdf_io,
                mimetype='application/pdf',
                as_attachment=True,
                download_name='resume.pdf'
            )

        except subprocess.CalledProcessError as e:
            print(f"resume-cli error: {e}")
            print(f"Command output: {e.output if hasattr(e, 'output') else 'No output'}")
            return jsonify({"error": f"Resume export failed: {str(e)}"}), 500
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return jsonify({"error": str(e)}), 500
        finally:
            # Clean up the temporary directory
            try:
                shutil.rmtree(tempdir)
                print(f"Cleaned up temporary directory: {tempdir}")
            except Exception as e:
                print(f"Error cleaning up temporary directory: {e}")

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Resume export failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
