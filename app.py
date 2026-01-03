import os
import json
import datetime
import qrcode
import fitz 
import shutil
import subprocess
import time
import zipfile
import io
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- KONFIGURATION ---
UPLOAD_FOLDER = 'static/uploads'
STATIC_FOLDER = 'static'
SETTINGS_FILE = 'settings.json'
FILES_DATA_FILE = 'files.json'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'pdf', 'zip'}
ADMIN_PASSWORD = 'admin' 

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'geheim_key_fuer_session_sicherheit'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
OVERRIDE_STATE = {'active': False, 'type': 'none', 'content': '', 'style': 'info'}

# --- DATEN MANAGEMENT ---

def load_settings():
    defaults = {
        'duration': 5000, 'rotation': 0, 'transition': 'fade',
        'layout': 'fullscreen', 'sidebar_title': 'Willkommen', 'sidebar_text': 'Infos...', 'sidebar_clock': True,
        
        # NEU: COUNTDOWN DEFAULTS
        'countdown_active': False, 'countdown_target': '', 'countdown_label': 'Start in:',

        'ticker_text': '', 'ticker_active': False, 'ticker_bg': '#cc0000', 'ticker_color': '#ffffff',
        'qr_active': False, 'qr_text': '',
        'weather_active': False, 'weather_city': '',
        'logo_active': False, 'logo_position': 'top-left'
    }
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f: json.dump(defaults, f)
    with open(SETTINGS_FILE, 'r') as f:
        data = json.load(f)
        for key, val in defaults.items():
            if key not in data: data[key] = val
        return data

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f: json.dump(data, f)

def load_file_data():
    if not os.path.exists(FILES_DATA_FILE): return {'files': {}, 'order': []}
    with open(FILES_DATA_FILE, 'r') as f: 
        data = json.load(f)
        if 'files' not in data: return {'files': data, 'order': []}
        return data

def save_file_data(data):
    with open(FILES_DATA_FILE, 'w') as f: json.dump(data, f)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_time(time_str):
    if not time_str or time_str.strip() == "": return ""
    try: return datetime.datetime.strptime(time_str.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        try: return datetime.datetime.strptime(time_str.strip(), "%H:%M").strftime("%H:%M")
        except: return ""

def is_time_in_range(start, end):
    if not start or not end: return True 
    now = datetime.datetime.now().time()
    try:
        s_time = datetime.datetime.strptime(start, "%H:%M").time()
        e_time = datetime.datetime.strptime(end, "%H:%M").time()
        if s_time < e_time: return s_time <= now <= e_time
        else: return now >= s_time or now <= e_time
    except ValueError: return True

def generate_qr_code(text):
    if not text: return
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(os.path.join(STATIC_FOLDER, 'qr_code.png'))
    except Exception as e: print(f"QR Fehler: {e}")

def process_pdf(pdf_path, filename):
    try:
        doc = fitz.open(pdf_path)
        base_name = filename.rsplit('.', 1)[0]
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150) 
            new_filename = f"{base_name}_seite_{i+1}.png"
            pix.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
        doc.close()
        os.remove(pdf_path)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False

def create_text_slide(text, bg_color, text_color):
    try:
        width, height = 1920, 1080
        img = Image.new('RGB', (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)
        font_path = "arial.ttf" 
        if os.name == 'posix':
            candidates = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
                          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                          "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
            for c in candidates:
                if os.path.exists(c): font_path = c; break
        try: font = ImageFont.truetype(font_path, 100)
        except: font = ImageFont.load_default()

        lines = []
        words = text.split()
        current_line = []
        for word in words:
            current_line.append(word)
            if len(" ".join(current_line)) > 25: 
                lines.append(" ".join(current_line[:-1]))
                current_line = [word]
        lines.append(" ".join(current_line))
        total_height = len(lines) * 110
        y_text = (height - total_height) / 2
        for line in lines:
            left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
            text_width = right - left
            x_text = (width - text_width) / 2
            draw.text((x_text, y_text), line, font=font, fill=text_color)
            y_text += 110

        filename = f"tafel_{int(time.time())}.png"
        img.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return True
    except Exception as e:
        print(f"Text Slide Error: {e}")
        return False

def get_system_stats():
    stats = {'temp': 'N/A', 'disk_total': 0, 'disk_used': 0, 'disk_percent': 0}
    try:
        total, used, free = shutil.disk_usage("/")
        stats['disk_total'] = round(total / (2**30), 1)
        stats['disk_used'] = round(used / (2**30), 1)
        stats['disk_percent'] = round((used / total) * 100, 1)
    except: pass
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) / 1000.0
            stats['temp'] = f"{temp}°C"
    except: stats['temp'] = "N/A"
    return stats

# --- ROUTEN ---

@app.route('/')
def index(): return redirect(url_for('display'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/download_backup')
def download_backup():
    if not session.get('logged_in'): return redirect(url_for('login'))
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(SETTINGS_FILE): zf.write(SETTINGS_FILE)
        if os.path.exists(FILES_DATA_FILE): zf.write(FILES_DATA_FILE)
        for root, dirs, files in os.walk(UPLOAD_FOLDER):
            for file in files:
                abs_path = os.path.join(root, file)
                zf.write(abs_path, os.path.join(UPLOAD_FOLDER, file))
        logo_path = os.path.join(STATIC_FOLDER, 'logo.png')
        if os.path.exists(logo_path): zf.write(logo_path, os.path.join(STATIC_FOLDER, 'logo.png'))
    memory_file.seek(0)
    return send_file(memory_file, download_name=f'bar_display_backup_{int(time.time())}.zip', as_attachment=True)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))

    settings = load_settings()
    file_data = load_file_data()
    files_meta = file_data.get('files', {})

    if request.method == 'POST':
        if 'override_action' in request.form:
            action = request.form['override_action']
            if action == 'stop': OVERRIDE_STATE['active'] = False
            elif action == 'message':
                OVERRIDE_STATE['active'] = True; OVERRIDE_STATE['type'] = 'text'; 
                OVERRIDE_STATE['content'] = request.form.get('override_text', ''); OVERRIDE_STATE['style'] = 'alert'
            elif action == 'happyhour':
                OVERRIDE_STATE['active'] = True; OVERRIDE_STATE['type'] = 'text'; 
                OVERRIDE_STATE['content'] = "🍹 HAPPY HOUR! 🍹\nAlle Cocktails 50%"; OVERRIDE_STATE['style'] = 'party'
            elif action == 'lastcall':
                OVERRIDE_STATE['active'] = True; OVERRIDE_STATE['type'] = 'text'; 
                OVERRIDE_STATE['content'] = "⚠️ LAST CALL ⚠️\nLetzte Runde bestellen!"; OVERRIDE_STATE['style'] = 'warning'
            return redirect(url_for('admin'))

        if 'sort_order' in request.form:
            try:
                new_order = json.loads(request.form['sort_order'])
                file_data['order'] = new_order
                save_file_data(file_data)
                return "OK"
            except: pass

        if 'system_action' in request.form:
            action = request.form['system_action']
            if action == 'reboot' and os.name != 'nt': os.system("sudo reboot")
            elif action == 'shutdown' and os.name != 'nt': os.system("sudo shutdown now")
            elif action == 'restore':
                if 'restore_file' in request.files:
                    f = request.files['restore_file']
                    if f and f.filename.endswith('.zip'):
                        shutil.rmtree(UPLOAD_FOLDER)
                        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                        if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
                        if os.path.exists(FILES_DATA_FILE): os.remove(FILES_DATA_FILE)
                        with zipfile.ZipFile(f, 'r') as zf: zf.extractall('.')
                        return redirect(url_for('admin'))

        # SETTINGS
        if 'duration' in request.form:
            settings['ticker_text'] = request.form.get('ticker_text', '')
            settings['ticker_active'] = 'ticker_active' in request.form
            settings['ticker_bg'] = request.form.get('ticker_bg', '#cc0000')
            settings['ticker_color'] = request.form.get('ticker_color', '#ffffff')
            settings['qr_text'] = request.form.get('qr_text', '')
            settings['qr_active'] = 'qr_active' in request.form
            settings['weather_city'] = request.form.get('weather_city', '')
            settings['weather_active'] = 'weather_active' in request.form
            settings['logo_active'] = 'logo_active' in request.form
            settings['logo_position'] = request.form.get('logo_position', 'top-left')
            settings['transition'] = request.form.get('transition', 'fade')
            settings['layout'] = request.form.get('layout', 'fullscreen')
            settings['sidebar_title'] = request.form.get('sidebar_title', '')
            settings['sidebar_text'] = request.form.get('sidebar_text', '')
            settings['sidebar_clock'] = 'sidebar_clock' in request.form
            
            # NEU: COUNTDOWN SETTINGS
            settings['countdown_active'] = 'countdown_active' in request.form
            settings['countdown_target'] = request.form.get('countdown_target', '')
            settings['countdown_label'] = request.form.get('countdown_label', 'Start in:')

            if settings['qr_text']: generate_qr_code(settings['qr_text'])
            try:
                settings['rotation'] = int(request.form.get('rotation', 0))
                val = int(request.form['duration'])
                if val > 0: settings['duration'] = val * 1000
            except ValueError: pass
            save_settings(settings)

        if 'create_text_slide' in request.form:
            text = request.form.get('slide_text', '')
            bg = request.form.get('slide_bg', '#000000')
            fg = request.form.get('slide_fg', '#ffffff')
            if text: create_text_slide(text, bg, fg)

        if 'logo_file' in request.files:
            file = request.files['logo_file']
            if file and '.' in file.filename: file.save(os.path.join(STATIC_FOLDER, 'logo.png'))
        if 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                if filename.lower().endswith('.pdf'): process_pdf(save_path, filename)
        
        changes_made = False
        for key, value in request.form.items():
            if key.startswith('start_'):
                filename = key.replace('start_', '')
                if filename not in files_meta: files_meta[filename] = {}
                files_meta[filename]['start'] = normalize_time(value)
                changes_made = True
            elif key.startswith('end_'):
                filename = key.replace('end_', '')
                if filename not in files_meta: files_meta[filename] = {}
                files_meta[filename]['end'] = normalize_time(value)
                changes_made = True
        if changes_made:
            file_data['files'] = files_meta
            save_file_data(file_data)

        if 'delete' in request.form:
            fname = request.form['delete']
            path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            if os.path.exists(path): os.remove(path)
            if fname in files_meta: del files_meta[fname]
            if fname in file_data.get('order', []): file_data['order'].remove(fname)
            file_data['files'] = files_meta
            save_file_data(file_data)
                
        return redirect(url_for('admin'))

    files_on_disk = sorted(os.listdir(app.config['UPLOAD_FOLDER']))
    saved_order = file_data.get('order', [])
    final_list = [f for f in saved_order if f in files_on_disk]
    for f in files_on_disk:
        if f not in final_list: final_list.append(f)
            
    files_with_data = []
    for f in final_list:
        data = files_meta.get(f, {'start': '', 'end': ''})
        files_with_data.append({'name': f, 'start': data.get('start', ''), 'end': data.get('end', '')})

    display_settings = settings.copy()
    display_settings['duration'] = int(display_settings['duration'] / 1000)
    system_stats = get_system_stats()

    return render_template('admin.html', files=files_with_data, settings=display_settings, stats=system_stats, override=OVERRIDE_STATE)

@app.route('/display')
def display(): return render_template('display.html')

@app.route('/api/data')
def get_data():
    files_on_disk = os.listdir(app.config['UPLOAD_FOLDER'])
    file_data = load_file_data()
    files_meta = file_data.get('files', {})
    saved_order = file_data.get('order', [])
    sorted_files = [f for f in saved_order if f in files_on_disk]
    for f in sorted_files: files_on_disk.remove(f)
    sorted_files.extend(sorted(files_on_disk))

    valid_files = []
    for f in sorted_files:
        if not allowed_file(f): continue
        meta = files_meta.get(f, {})
        if is_time_in_range(meta.get('start', ''), meta.get('end', '')):
            ext = f.rsplit('.', 1)[1].lower()
            valid_files.append({
                'url': url_for('static', filename='uploads/' + f),
                'type': 'video' if ext == 'mp4' else 'image'
            })
    
    return jsonify({
        'files': valid_files, 
        'settings': load_settings(),
        'override': OVERRIDE_STATE
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8030, debug=False)