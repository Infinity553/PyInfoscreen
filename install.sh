#!/bin/bash

# --- KONFIGURATION ---
# Hier deine GitHub URL eintragen!
REPO_URL="https://github.com/Infinity553/PyInfoscreen.git"
APP_DIR="/home/pi/bar_display"
USER="pi"

echo "🍺 --- START: Bar Display Installation ---"

# 1. System Updates & Abhängigkeiten
echo "📦 Installiere System-Pakete..."
sudo apt-get update
# build-essential und lib-devs sind wichtig für Pillow/PyMuPDF
sudo apt-get install -y python3-venv python3-pip git chromium-browser unclutter build-essential libjpeg-dev zlib1g-dev

# 2. Repository Klonen
if [ -d "$APP_DIR" ]; then
    echo "⚠️ Ordner existiert bereits. Überspringe Clone."
else
    echo "⬇️ Klone Repository..."
    git clone "$REPO_URL" "$APP_DIR"
fi

# 3. Python Umgebung einrichten (VENV)
echo "🐍 Richte Python Virtual Environment ein..."
cd "$APP_DIR"
# Venv erstellen
python3 -m venv venv
# Venv aktivieren und Pakete installieren
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install flask "qrcode[pil]" pymupdf Pillow

# 4. Systemd Service für Python Backend erstellen
echo "⚙️ Erstelle Autostart Service (Backend)..."
SERVICE_FILE="/etc/systemd/system/bardisplay.service"

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Bar Display Backend
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
# Wir nutzen das Python aus dem venv!
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Service aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable bardisplay.service
sudo systemctl start bardisplay.service

# 5. Kiosk Mode Autostart (Frontend)
echo "🖥️ Richte Chromium Kiosk Mode ein..."
AUTOSTART_DIR="/home/$USER/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/kiosk.desktop" <<EOL
[Desktop Entry]
Type=Application
Name=Kiosk
Exec=/usr/bin/chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:8030/display --check-for-update-interval=31536000
X-GNOME-Autostart-enabled=true
EOL

# 6. Mauszeiger verstecken (Unclutter)
# Unclutter startet meist automatisch, wir stellen sicher, dass es in den X-Session Einstellungen ist
# (Optional, da apt install unclutter meist reicht, aber sicher ist sicher)
if ! grep -q "unclutter" /etc/xdg/lxsession/LXDE-pi/autostart 2>/dev/null; then
    # Versuche es global hinzuzufügen, falls die Datei existiert
    if [ -f /etc/xdg/lxsession/LXDE-pi/autostart ]; then
        sudo bash -c "echo '@unclutter -idle 0.1' >> /etc/xdg/lxsession/LXDE-pi/autostart"
    fi
fi

# 7. Abschluss
echo "✅ Installation fertig!"
echo "👉 Das Backend läuft bereits."
echo "👉 Bitte starte den Raspberry Pi jetzt neu: sudo reboot"
