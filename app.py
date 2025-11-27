from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import sqlite3
import json
import datetime

# TRY IMPORTING OCR LIBRARIES
try:
    from PIL import Image
    import pytesseract
    # Tesseract Path
    pytesseract.pytesseract.tesseract_cmd = r"D:\tessaract\tesseract.exe"
except ImportError:
    print("WARNING: 'pytesseract' or 'Pillow' not installed. OCR will not work.")

# CONFIGURATION
app = Flask(__name__, static_folder='.')
CORS(app)
DB_NAME = "chandas.db"

# --------------------------
# DATABASE SETUP
# --------------------------
def init_db():
    """Initialize the SQLite database and create the history table."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  text TEXT,
                  overall_type TEXT,
                  result_json TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# --------------------------
# LOGIC CLASS
# --------------------------
class KannadaChandasIdentifier:
    def __init__(self):
        self.LAGHU = 'U'
        self.GURU = '-'
        self.VOWELS_SHORT = {'ಅ', 'ಇ', 'ಉ', 'ಋ', 'ಎ', 'ಒ'}
        self.VOWELS_LONG = {'ಆ', 'ಈ', 'ಊ', 'ಏ', 'ಐ', 'ಓ', 'ಔ', 'ೠ', 'ೡ'}
        self.YOGAVAHAS = {'ಂ', 'ಃ'}
        self.VIRAMA = '್'
        self.VS_SHORT = {'ಿ', 'ು', 'ೃ', 'ೆ', 'ೊ'}
        self.VS_LONG = {'ಾ', 'ೀ', 'ೂ', 'ೇ', 'ೈ', 'ೋ', 'ೌ', 'ೄ'}
        self.GANAS = {
            'Ma': [self.GURU, self.GURU, self.GURU], 'Ya': [self.LAGHU, self.GURU, self.GURU],
            'Ra': [self.GURU, self.LAGHU, self.GURU], 'Sa': [self.LAGHU, self.LAGHU, self.GURU],
            'Ta': [self.GURU, self.GURU, self.LAGHU], 'Ja': [self.LAGHU, self.GURU, self.LAGHU],
            'Bha': [self.GURU, self.LAGHU, self.LAGHU], 'Na': [self.LAGHU, self.LAGHU, self.LAGHU]
        }

    def clean_text(self, text):
        text = re.sub(r'[^\u0C80-\u0CFF\s]', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def get_laghu_guru_sequence(self, text):
        clean_text = [char for char in text if '\u0c80' <= char <= '\u0cff' or char == ' ']
        weights = []
        i = 0
        while i < len(clean_text):
            char = clean_text[i]
            if char.isspace():
                i += 1
                continue
            current_weight = self.LAGHU
            if char in self.VOWELS_LONG: current_weight = self.GURU
            elif char in self.VOWELS_SHORT: current_weight = self.LAGHU
            elif '\u0c90' <= char <= '\u0cb9':
                if i + 1 < len(clean_text):
                    next_char = clean_text[i+1]
                    if next_char in self.VS_LONG:
                        current_weight = self.GURU
                        i += 1
                    elif next_char in self.VS_SHORT:
                        current_weight = self.LAGHU
                        i += 1
                    elif next_char == self.VIRAMA:
                        if weights: weights[-1] = self.GURU
                        i += 2
                        continue
                else: current_weight = self.LAGHU
            if i + 1 < len(clean_text) and clean_text[i+1] in self.YOGAVAHAS:
                current_weight = self.GURU
                i += 1
            if i + 1 < len(clean_text):
                peek = clean_text[i+1]
                if '\u0c90' <= peek <= '\u0cb9' and i + 2 < len(clean_text) and clean_text[i+2] == self.VIRAMA:
                    current_weight = self.GURU
            weights.append(current_weight)
            i += 1
        return weights

    def identify_ganas(self, weights):
        ganas, rem = [], len(weights) % 3
        for i in range(0, len(weights) - rem, 3):
            chunk = weights[i:i+3]
            match = next((n for n, p in self.GANAS.items() if chunk == p), "?")
            ganas.append(match)
        res = "-".join(ganas)
        if rem:
            res += "-" + "-".join(["La" if w == self.LAGHU else "Ga" for w in weights[-rem:]])
        return res

    def analyze_single_stanza(self, text_block):
        cleaned_block = self.clean_text(text_block)
        lines = [l.strip() for l in cleaned_block.split('\n') if l.strip()]
        analysis = []
        for line in lines:
            w = self.get_laghu_guru_sequence(line)
            g = self.identify_ganas(w)
            m = sum(1 if x == self.LAGHU else 2 for x in w)
            cnt = len(w)
            match = "Unknown"
            if cnt == 20 and "Bha-Ra-Na-Bha-Bha-Ra-La-Ga" in g: match = "Utpalamala"
            elif cnt == 21 and "Na-Ja-Bha-Ja-Ja-Ja-Ra" in g: match = "Champakamala"
            elif cnt == 19 and "Ma-Sa-Ja-Sa-Ta-Ta-Ga" in g: match = "Shardulavikridita"
            elif cnt == 20 and "Sa-Bha-Ra-Na-Ma-Ya-La-Ga" in g: match = "Mattebhavikridita"
            elif cnt == 21 and "Ma-Ra-Bha-Na-Ya-Ya-Ya" in g: match = "Sragdhara"
            elif cnt == 14 and "Na-Na-Ma-Ya-Ya" in g: match = "Malini"
            elif cnt == 20 and g.startswith("Bha-Ra-Na"): match = "Utpalamala (Variant?)"
            analysis.append({"line": line, "pattern": w, "ganas": g, "matras": m, "match": match})
        overall = "Unknown / Vruttha"
        if len(lines) == 4:
            ms = [x['matras'] for x in analysis]
            if (11<=ms[0]<=13) and (19<=ms[1]<=21) and (11<=ms[2]<=13) and (19<=ms[3]<=21):
                overall = "Kanda Padya (ಕಂದ ಪದ್ಯ)"
        elif len(lines) == 6:
            ms = [x['matras'] for x in analysis]
            if (12<=ms[0]<=16) and (20<=ms[2]<=26):
                overall = "Shatpadi (ಷಟ್ಪದಿ)"
        vruttha_counts = {}
        for l in analysis:
            if l['match'] != "Unknown":
                vruttha_counts[l['match']] = vruttha_counts.get(l['match'], 0) + 1
        if vruttha_counts:
            most_common = max(vruttha_counts, key=vruttha_counts.get)
            if vruttha_counts[most_common] >= len(lines) / 2:
                overall = most_common
        return {"overallType": overall, "lines": analysis}

    def analyze_full_poem(self, text):
        raw_stanzas = re.split(r'\n\s*\n', text.strip())
        results = []
        for index, raw_stanza in enumerate(raw_stanzas):
            if not raw_stanza.strip():
                continue
            stanza_analysis = self.analyze_single_stanza(raw_stanza)
            stanza_analysis['id'] = index + 1
            results.append(stanza_analysis)
        return {"stanzas": results}

identifier = KannadaChandasIdentifier()

# --------------------------
# WEB ROUTES
# --------------------------

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        if not data or 'text' not in data: return jsonify({"error": "No text"}), 400
        
        # 1. Perform Analysis
        result = identifier.analyze_full_poem(data['text'])
        
        # 2. AUTO-SAVE LOGIC (For Dataset Building)
        # Check if the result is valid enough to be a dataset entry
        should_save = False
        overall_type_db = "Unknown"
        
        for stanza in result['stanzas']:
            # Case A: Stanza itself is identified (Kanda, Shatpadi, etc.)
            if stanza['overallType'] not in ["Unknown / Vruttha", "Unknown"]:
                should_save = True
                overall_type_db = stanza['overallType']
                break 
            
            # Case B: At least one line is identified (Vruttas)
            for line in stanza['lines']:
                if line['match'] != "Unknown":
                    should_save = True
                    overall_type_db = line['match']
                    break
            if should_save: break

        # 3. Insert into DB if Valid AND Not Duplicate
        if should_save:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            
            # Check for duplicates to prevent dataset pollution
            c.execute("SELECT id FROM history WHERE text = ?", (data['text'],))
            exists = c.fetchone()
            
            if not exists:
                c.execute("INSERT INTO history (text, overall_type, result_json) VALUES (?, ?, ?)", 
                          (data['text'], overall_type_db, json.dumps(result)))
                conn.commit()
                print(f"Dataset Update: Saved valid entry -> {overall_type_db}")
            else:
                print("Dataset Update: Skipped duplicate entry.")
            
            conn.close()

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/ocr', methods=['POST'])
def ocr_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    try:
        image = Image.open(file.stream)
        text = pytesseract.image_to_string(image, lang='kan+eng')
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": f"OCR Error: {str(e)}"}), 500

@app.route('/history', methods=['GET'])
def get_history():
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        c.execute("SELECT id, text, overall_type, timestamp FROM history ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                "id": row["id"],
                "text": row["text"][:50] + "..." if len(row["text"]) > 50 else row["text"], 
                "full_text": row["text"], 
                "overall_type": row["overall_type"],
                "timestamp": row["timestamp"]
            })
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Keep this for explicit saves if needed, but analyze covers auto-save now
@app.route('/save', methods=['POST'])
def save_result():
    try:
        data = request.json
        # ... logic similar to above ...
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("SUCCESS! Server is running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)