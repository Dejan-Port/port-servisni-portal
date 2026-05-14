#!/bin/bash
# Port Servisni Portal — Linux Standalone Instalacija
# Testirano na Ubuntu 20.04+ i Debian 11+

set -e

APP_DIR="/opt/portservis"
SERVICE_NAME="portservis"
PORT=8080

echo "================================================"
echo "  Port Servisni Portal — Linux Instalacija"
echo "================================================"
echo ""

# Proveri root
if [ "$EUID" -ne 0 ]; then
    echo "Pokrenite kao root: sudo bash install.sh"
    exit 1
fi

# Proveri OS
if ! command -v apt-get &> /dev/null; then
    echo "Ova skripta podrzava samo Debian/Ubuntu sisteme."
    exit 1
fi

echo "[1/7] Instalacija sistemskih zavisnosti..."
apt-get update -q
apt-get install -y python3 python3-pip python3-venv curl wget

echo "[2/7] Kreiranje direktorijuma..."
mkdir -p "$APP_DIR"/{html,db,logs,firebird/lib}
mkdir -p /etc/portservis

echo "[3/7] Kopiranje fajlova..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/resources/server.py"          "$APP_DIR/"
cp "$SCRIPT_DIR/resources/version.txt"        "$APP_DIR/" 2>/dev/null || echo "1.0.2" > "$APP_DIR/version.txt"
cp "$SCRIPT_DIR/resources/html/index.html"    "$APP_DIR/html/"
cp "$SCRIPT_DIR/resources/html/changelog.html" "$APP_DIR/html/"

# Firebird client library
FB_LIB=$(find /usr/lib -name "libfbclient.so*" 2>/dev/null | head -1)
if [ -n "$FB_LIB" ]; then
    ln -sf "$FB_LIB" "$APP_DIR/firebird/lib/libfbclient.so"
    echo "  Firebird lib: $FB_LIB"
else
    echo "  UPOZORENJE: libfbclient.so nije pronadjen!"
fi

echo "[4/7] Kreiranje Python virtualnog okruzenja..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install fastapi "uvicorn[standard]" firebird-driver python-multipart cryptography -q

echo "[5/7] Kopiranje baze podataka..."
if [ -f "$APP_DIR/db/servis.gdb" ]; then
    echo "  Baza vec postoji, preskacam."
else
    cp "$SCRIPT_DIR/resources/servis.gdb" "$APP_DIR/db/servis.gdb"
    chown root:root "$APP_DIR/db/servis.gdb"
    chmod 660 "$APP_DIR/db/servis.gdb"
    echo "  Baza kopirana."
fi

echo "[6/7] Kreiranje systemd servisa..."
cat > /etc/systemd/system/portservis.service << SVCEOF
[Unit]
Description=Port Servisni Portal
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/logs/server.log
StandardError=append:$APP_DIR/logs/server_err.log

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable portservis
systemctl start portservis

echo "[7/7] Provera..."
sleep 3
if curl -s "http://localhost:$PORT/health" | grep -q "ok"; then
    echo "  Server radi!"
else
    echo "  UPOZORENJE: Server mozda nije pokrenut. Proveri: journalctl -u portservis -n 20"
fi

echo ""
echo "================================================"
echo "  Instalacija zavrsena!"
echo "  Portal je dostupan na: http://localhost:$PORT"
echo "  Logovi: $APP_DIR/logs/"
echo "  Upravljanje: sudo systemctl start|stop|restart portservis"
echo "================================================"
