# Port Servisni Portal

Servisni portal za upravljanje radnim nalozima, klijentima i servisnom dokumentacijom.

---

## Standalone verzija (Windows)

### Zahtevi
- Windows 10 64-bit
- Administrator prava (za instalaciju)
- Internet (samo pri prvoj instalaciji za Python pakete)

### Instalacija

1. Preuzmi `PortServis-latest.zip` sa `https://servisport.rs/servisni/download/`
2. Raspakuj ZIP
3. Desni klik na `INSTALL.bat` → **Pokreni kao administrator**
4. Prati uputstvo na ekranu

Aplikacija se instalira u `C:\PortServis\` i automatski se pokreće sa Windowsom.

Ukoliko se aplikacija ne pokrene proveriti status za Port Servisni Portal u Task Scheduler Queued ili Running, ukoliko je Queued pokrenuti ga i aplikacija ce se otvoriti u pretrazivacu, bug je primecen na nekim Win11 sistemima, bice update cim se resi.

### Nakon instalacije

Obavezno popuni podatke o firmi:
1. Otvori `http://localhost:8080`
2. Podešavanja → 🏢 Podaci firme
3. Unesi: Naziv *, Mesto *, Email *, Mobilni telefon *
4. Opciono: Napomena na reversu

### Update

Aplikacija automatski provjerava novu verziju pri svakom pokretanju. Kada je dostupna nova verzija, prikazuje se notifikacija u portalu.

### Deinstalacija

```bat
schtasks /delete /tn "PortServisniPortal" /f
rmdir /s /q C:\PortServis
```

---

## Build & Release

### Pakovanje nove verzije

1. Ažuriraj `VERSION` u `server.py`
2. Ažuriraj `html\changelog.html`
3. Pokreni build skriptu:

```bat
C:\PortServis\python\python.exe build_release.py
```

4. Upload na server:

```bash
scp C:\PortServis\releases\PortServis-latest.zip XXXXXX@servisport.rs:/var/www/html/servisni/download/
```

5. Ažuriraj `version.json`:

```json
{
  "version": "1.0.X",
  "notes": "Opis izmena",
  "url": "https://servisport.rs/servisni/download/PortServis-latest.zip",
  "date": "YYYY-MM-DD"
}
```

### Slanje novosti korisnicima

```bash
sudo nano /var/www/html/updates/standalone_news.json
```

```json
{
  "news_id": "YYYY-MM-DD-001",
  "naslov": "Naslov poruke",
  "poruka": "Tekst poruke...",
  "tip": "info"
}
```

`tip` može biti: `info`, `success`, `warning`

---

## Preuzimanje

```
https://servisport.rs/servisni/download/PortServis-latest.zip
```

Ili kloniraj repozitorijum:

```bash
git clone https://github.com/Dejan-Port/port-servisni-portal.git
```

## Struktura projekta

```
port-servisni-portal/
├── server.py             ← Backend
├── html/
│   ├── index.html        ← Frontend
│   └── changelog.html
├── windows/
│   ├── INSTALL.bat       ← Instalacija
│   ├── build_release.py  ← Build skripta
│   ├── init_db.py        ← Inicijalizacija baze
│   ├── alter_napomena.py ← Dodavanje NAPOMENA_REVERS
│   └── create_tables.py  ← Kreiranje tabela
└── README.md
```

---

## Git

```bash
git init
git add server.py html\index.html html\changelog.html INSTALL.bat README.md .gitignore
git commit -m "Port Servisni Portal v1.0.0"
git remote add origin https://github.com/tvoj-nalog/port-servisni-portal.git
git branch -M main
git push -u origin main
```

**.gitignore:**
```
db/
logs/
*.gdb
*.enc
version.txt
__pycache__/
releases/
*.dll
*.dat
*.msg
python/
plugins/
```

## Tehnologije

- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Baza**: Firebird 3.0 (embedded)
- **Frontend**: Vanilla JS, CSS custom properties
- **Windows servis**: Task Scheduler

---

## Licenca

MIT License — slobodan softver, otvorenog koda.

Možete koristiti, kopirati, modifikovati i distribuirati bez ograničenja.

### Zahtevi
- Windows 10 64-bit
- Administrator prava (za instalaciju)
- Internet (samo pri prvoj instalaciji za Python pakete)

### Instalacija

1. Preuzmi `PortServis-latest.zip` sa `https://servisport.rs/servisni/download/`
2. Raspakuj ZIP
3. Desni klik na `INSTALL.bat` → **Pokreni kao administrator**
4. Prati uputstvo na ekranu

Aplikacija se instalira u `C:\PortServis\` i automatski se pokreće sa Windowsom.

### Nakon instalacije

Obavezno popuni podatke o firmi:
1. Otvori `http://localhost:8080`
2. Podešavanja → 🏢 Podaci firme
3. Unesi: Naziv *, Mesto *, Email *, Mobilni telefon *
4. Opciono: Napomena na reversu

### SMTP podešavanja

Ako koristiš lokalni SMTP (nije obavezno — prijava problema ide direktno na servisport.rs):

```bat
C:\PortServis\python\python.exe smtp_setup.py
```

### Update

Aplikacija automatski provjerava novu verziju pri svakom pokretanju. Kada je dostupna nova verzija, prikazuje se notifikacija u portalu.

Ručni update:
```bat
C:\PortServis\python\python.exe -m pip install --upgrade ...
```

### Deinstalacija

```bat
schtasks /delete /tn "PortServisniPortal" /f
rmdir /s /q C:\PortServis
```

---

## Build & Release

### Pakovanje nove verzije

1. Ažuriraj `VERSION` u `standalone/server.py`
2. Ažuriraj `changelog.html`
3. Pokreni build skriptu na Windows mašini:

```bat
C:\PortServis\python\python.exe build_release.py
```

4. Upload na server:

```bash
scp C:\PortServis\releases\PortServis-latest.zip port@servisport.rs:/var/www/html/servisni/download/
```

5. Ažuriraj `version.json` na serveru:

```bash
sudo nano /var/www/html/updates/version.json
```

```json
{
  "version": "1.0.X",
  "notes": "Opis izmena",
  "url": "https://servisport.rs/servisni/download/PortServis-latest.zip",
  "date": "YYYY-MM-DD"
}
```

### Slanje novosti korisnicima

```bash
# Standalone korisnici
sudo nano /var/www/html/updates/standalone_news.json

# Server korisnici  
sudo nano /var/www/html/updates/server_news.json
```

JSON format:
```json
{
  "news_id": "YYYY-MM-DD-001",
  "naslov": "Naslov poruke",
  "poruka": "Tekst poruke...",
  "tip": "info"
}
```

`tip` može biti: `info`, `success`, `warning`

Promeni `news_id` da se poruka ponovo prikaže svim korisnicima.

---

## Preuzimanje

Preuzmi najnoviju verziju:

```
https://servisport.rs/servisni/download/PortServis-latest.zip
```

Ili kloniraj repozitorijum:

```bash
git clone https://github.com/tvoj-nalog/port-servisni-portal.git
```

## Struktura projekta

```
port-servisni-portal/
├── server_final.py           ← Server verzija backend
├── index_new.html            ← Server verzija frontend (source)
├── index_final.html          ← Server verzija frontend (sa logom)
├── changelog.html            ← Changelog stranica
├── add_napomena.sql          ← SQL za dodavanje NAPOMENA_REVERS kolone
├── standalone/
│   ├── server.py             ← Standalone backend
│   ├── html/
│   │   ├── index.html        ← Standalone frontend
│   │   └── changelog.html
│   ├── standalone_news.json
│   ├── server_news.json
│   └── windows/
│       ├── INSTALL.bat       ← Instalacija
│       ├── build_release.py  ← Build skripta
│       ├── smtp_setup.py     ← SMTP podešavanja
│       ├── init_db.py        ← Inicijalizacija baze
│       ├── alter_smtp.py     ← Proširenje SMTP kolona
│       ├── alter_napomena.py ← Dodavanje NAPOMENA_REVERS
│       └── create_tables.py  ← Kreiranje tabela
└── README.md
```

---

## Git

```bash
git init
git add server.py html\index.html html\changelog.html INSTALL.bat README.md .gitignore
git commit -m "Port Servisni Portal v1.0.0"
git remote add origin https://github.com/tvoj-nalog/port-servisni-portal.git
git branch -M main
git push -u origin main
```

**.gitignore:**
```
db/
logs/
*.gdb
*.enc
version.txt
__pycache__/
releases/
*.dll
*.dat
*.msg
python/
plugins/
```

## Tehnologije

- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Baza**: Firebird 3.0 (embedded za standalone)
- **Frontend**: Vanilla JS, CSS custom properties
- **Autentifikacija**: JWT + 2FA (TOTP) — server verzija
- **Enkripcija**: Fernet (AES-128-CBC) — standalone SMTP
- **Windows servis**: Task Scheduler

---

## Licenca

MIT License — slobodan softver, otvorenog koda.

Možete koristiti, kopirati, modifikovati i distribuirati bez ograničenja.
