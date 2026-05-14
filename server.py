"""
Port Servisni Portal — Standalone verzija v1.0.0
"""

import os as _os, sys as _sys

# ── Postavi PATH pre svih importa da Windows nadji fbclient zavisnosti ──
_app_dir = _os.path.dirname(_os.path.abspath(__file__))
_fb_path = _os.environ.get("FIREBIRD_CLIENT") or _os.path.join(_app_dir, "fbclient.dll")
_fb_dir  = _os.path.dirname(_fb_path)

# Dodaj sve foldere u DLL search path
for _d in [_fb_dir, _os.path.join(_fb_dir, "plugins")]:
    if _os.path.exists(_d):
        try: _os.add_dll_directory(_d)
        except: pass

# Postavi PATH
_os.environ["PATH"] = _fb_dir + ";" + _os.path.join(_fb_dir, "plugins") + ";" + _os.environ.get("PATH", "")
_os.environ["FIREBIRD"] = _fb_dir

# Ucitaj fbclient.dll eksplicitno kroz ctypes pre firebird.driver importa
import ctypes as _ctypes
try:
    _ctypes.WinDLL(_fb_path)
except Exception as _e:
    pass

import os, hashlib, json, base64
from datetime import datetime, timedelta, date
from typing import Optional

try:
    from firebird.driver import connect as _fb_connect, create_database as _fb_create
    _USE_DRIVER = True
except ImportError:
    _USE_DRIVER = False

import logging
logging.basicConfig(
    filename=r'C:\PortServis\logs\server.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(message)s'
)

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

VERSION    = "1.0.2"
_sdir      = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.environ.get("DB_PATH",    os.path.join(_sdir, "db", "servis.gdb"))
DB_USER    = "SYSDBA"
DB_PASSWORD= os.environ.get("FB_PASSWORD","masterkey")
DB_CHARSET = "UTF8"
STATIC_DIR = os.environ.get("STATIC_DIR",  os.path.join(_sdir, "html"))
UPDATE_URL    = os.environ.get("UPDATE_URL",    "https://servisport.rs/updates/version.json")
PRIJAVA_URL   = os.environ.get("PRIJAVA_URL",   "https://servisport.rs:8444/api/prijava")
STANDALONE_KEY = os.environ.get("STANDALONE_KEY", "port-standalone-2026-tajni")

def _machine_key():
    import platform
    try:
        if platform.system() == "Windows":
            import subprocess
            r = subprocess.run(["wmic","csproduct","get","UUID"],capture_output=True,text=True,timeout=5)
            mid = [l.strip() for l in r.stdout.splitlines() if l.strip() and l.strip()!="UUID"]
            machine_id = mid[0] if mid else "fallback"
        else:
            with open("/etc/machine-id") as f: machine_id = f.read().strip()
    except: machine_id = "fallback-machine-id"
    return base64.urlsafe_b64encode(hashlib.sha256(f"port-servis-{machine_id}".encode()).digest())

def encrypt_str(v):
    if not v: return v
    try:
        from cryptography.fernet import Fernet
        return Fernet(_machine_key()).encrypt(v.encode()).decode()
    except: return v

def decrypt_str(v):
    if not v: return v
    try:
        from cryptography.fernet import Fernet
        return Fernet(_machine_key()).decrypt(v.encode()).decode()
    except: return v

import os
os.makedirs(r'C:\PortServis\logs', exist_ok=True)

app = FastAPI(title="Port Servisni Portal", version=VERSION, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer(auto_error=False)

@app.middleware("http")
async def log_errors(request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            logging.error(f"500 error: {request.method} {request.url}")
        return response
    except Exception as e:
        logging.exception(f"Unhandled error: {request.method} {request.url}")
        raise

@app.on_event("startup")
async def on_startup():
    # Upisi verziju u fajl da JS moze da procita
    try:
        with open(os.path.join(_sdir, "version.txt"), "w") as _vf:
            _vf.write(VERSION)
    except:
        pass
    import asyncio, webbrowser, platform
    if platform.system() == "Windows":
        async def _open():
            await asyncio.sleep(1.5)
            webbrowser.open("http://localhost:8080")
        asyncio.create_task(_open())

def _set_fbclient():
    if _USE_DRIVER:
        import platform
        if platform.system() == "Windows":
            # Provjeri FIREBIRD_CLIENT env varijablu, pa _sdir
            _fb = os.environ.get("FIREBIRD_CLIENT") or os.path.join(_sdir, "fbclient.dll")
            if os.path.exists(_fb):
                try:
                    from firebird.driver import driver_config
                    if not driver_config.fb_client_library.value:
                        driver_config.fb_client_library.value = _fb
                    _fb_dir = os.path.dirname(_fb)
                    os.environ["FIREBIRD"] = _fb_dir
                    # Dodaj u PATH da Windows može naći zavisnosti
                    current_path = os.environ.get("PATH", "")
                    if _fb_dir not in current_path:
                        os.environ["PATH"] = _fb_dir + ";" + current_path
                except Exception as e:
                    pass

def get_db():
    _set_fbclient()
    if _USE_DRIVER:
        return _fb_connect(database=DB_PATH, user=DB_USER, password=DB_PASSWORD, charset=DB_CHARSET)
    import fdb
    return fdb.connect(database=DB_PATH, user=DB_USER, password=DB_PASSWORD, charset=DB_CHARSET)

class _DBCtx:
    def __init__(self): self.con = None
    def __enter__(self): self.con = get_db(); return self.con
    def __exit__(self, *a):
        if self.con:
            try: self.con.close()
            except: pass

def get_db_ctx(): return _DBCtx()

def rows_to_dicts(cur):
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def serialize(obj):
    if isinstance(obj, datetime): return obj.strftime("%d.%m.%Y %H:%M")
    if isinstance(obj, date): return obj.strftime("%d.%m.%Y")
    if isinstance(obj, (bytes, bytearray)): return None
    return obj

def clean(d):
    if isinstance(d, dict): return {k: clean(v) for k, v in d.items()}
    return serialize(d)

def ensure_db():
    if os.path.exists(DB_PATH): return
    print(f"  Kreiram bazu: {DB_PATH}")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    _set_fbclient()
    if _USE_DRIVER:
        try:
            _fb_create(database=DB_PATH, user=DB_USER, password=DB_PASSWORD, charset="UTF8")
            print("  Baza kreirana!")
        except Exception as e:
            print(f"  Greška: {e}")

def get_current_user(token: Optional[str]=None,
                     credentials: HTTPAuthorizationCredentials=Depends(security)) -> dict:
    return {"id": 1, "uname": "admin", "vrsta": 1}

def require_admin(user=Depends(get_current_user)): return user

class KlijentCreate(BaseModel):
    naziv: str = ""; ime: Optional[str]=None; prezime: Optional[str]=None
    firma_naziv: Optional[str]=None; mesto: str; adresa: Optional[str]=None
    tel_mobilni: Optional[str]=None; tel_fiksni: Optional[str]=None
    email: Optional[str]=None; pib: Optional[str]=None; mb: Optional[str]=None
    napomena: Optional[str]=None

class NalogCreate(BaseModel):
    klijent: int; uredjaj: str; serbr: Optional[str]=None
    opis_kvara: Optional[str]=None; garancija: int=0; kablovi: int=0
    ambalaza: int=0; drajveri: int=0; ostalo: int=0

class RealizacijaData(BaseModel):
    izvrseni_radovi: Optional[str]=None; cena: Optional[float]=None

class NalogLogCreate(BaseModel):
    status: str; beleska: Optional[str]=None

class FirmaUpdate(BaseModel):
    naziv: Optional[str]=None; mesto: Optional[str]=None; adresa: Optional[str]=None
    pib: Optional[str]=None; mb: Optional[str]=None; email: Optional[str]=None
    web: Optional[str]=None; tel_fiksni: Optional[str]=None; tel_mobilni: Optional[str]=None
    napomena_revers: Optional[str]=None

class SmtpConfig(BaseModel):
    smtp_host: Optional[str]=None; smtp_port: int=587; smtp_user: Optional[str]=None
    smtp_pass: Optional[str]=None; smtp_from: Optional[str]=None
    smtp_to: Optional[str]=None; smtp_ssl: int=0

class PrijavaProblema(BaseModel):
    naslov: str; poruka: str; prioritet: str="Normalan"

class LozinkaChange(BaseModel):
    stara_lozinka: str; nova_lozinka: str

class KorisnikCreate(BaseModel):
    uname: str; password: str; naziv: str; vrsta: int=0


@app.get("/changelog", include_in_schema=False)
def changelog():
    try:
        with open(os.path.join(STATIC_DIR, "changelog.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Changelog nije pronađen</h1>", 404)

@app.get("/", include_in_schema=False)
def root(): return RedirectResponse("/index.html")

@app.get("/index.html", include_in_schema=False)
def index_page():
    try:
        with open(f"{STATIC_DIR}/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse(f"<h1>index.html nije pronađen: {STATIC_DIR}</h1>", 404)

@app.get("/health", include_in_schema=False)
def health(): return {"status": "ok", "version": VERSION}

@app.get("/version.txt", include_in_schema=False)
def version_txt():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(VERSION)

@app.get("/auto-token", include_in_schema=False)
def auto_token(): return {"token": "standalone", "uname": "admin", "vrsta": 1}

@app.get("/firma", tags=["Firma"])
def get_firma(user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM FIRMA WHERE SIFRA=1")
        row = cur.fetchone()
        if not row: raise HTTPException(404, "Firma nije pronađena")
        return clean(dict(zip([d[0].lower() for d in cur.description], row)))

@app.put("/firma", tags=["Firma"])
def update_firma(data: FirmaUpdate, user=Depends(require_admin)):
    import re
    # Validacija obaveznih polja
    nedostaje = []
    if not data.naziv or not data.naziv.strip():
        nedostaje.append("Naziv firme")
    if not data.mesto or not data.mesto.strip():
        nedostaje.append("Mesto")
    if not data.email or not data.email.strip():
        nedostaje.append("Email")
    if not data.tel_mobilni or not data.tel_mobilni.strip():
        nedostaje.append("Mobilni telefon")
    if nedostaje:
        raise HTTPException(400, f"Obavezna polja: {', '.join(nedostaje)}")

    # Validacija formata
    greske = []

    # Email format
    if data.email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', data.email.strip()):
        greske.append("Email nije ispravan format")

    # Telefoni — samo cifre, +, razmaci i crtice
    tel_pattern = r'^[\+\d\s\-\(\)]+$'
    if data.tel_mobilni and not re.match(tel_pattern, data.tel_mobilni.strip()):
        greske.append("Mobilni telefon sadrži nedozvoljene znakove (dozvoljeno: cifre, +, razmak, -)")
    if data.tel_fiksni and not re.match(tel_pattern, data.tel_fiksni.strip()):
        greske.append("Fiksni telefon sadrži nedozvoljene znakove (dozvoljeno: cifre, +, razmak, -)")

    # PIB — samo cifre, tačno 9
    if data.pib and data.pib.strip():
        if not re.match(r'^\d{9}$', data.pib.strip()):
            greske.append("PIB mora imati tačno 9 cifara")

    # Matični broj — samo cifre, tačno 8
    if data.mb and data.mb.strip():
        if not re.match(r'^\d{8}$', data.mb.strip()):
            greske.append("Matični broj mora imati tačno 8 cifara")

    if greske:
        raise HTTPException(400, " | ".join(greske))

    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("UPDATE FIRMA SET NAZIV=?,MESTO=?,ADRESA=?,PIB=?,MB=?,EMAIL=?,WEB=?,TEL_FIKSNI=?,TEL_MOBILNI=?,NAPOMENA_REVERS=? WHERE SIFRA=1",
                    [data.naziv,data.mesto,data.adresa,data.pib,data.mb,data.email,data.web,data.tel_fiksni,data.tel_mobilni,data.napomena_revers])
        con.commit()
    return {"status": "updated"}

@app.get("/dashboard/stats", tags=["Dashboard"])
def dashboard_stats(user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM RADNI_NALOZI WHERE DATUM_REALIZACIJE IS NULL")
        aktivni = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM RADNI_NALOZI WHERE DATUM_REALIZACIJE IS NOT NULL")
        realizovani = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM KLIJENTI")
        klijenti = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM RADNI_NALOZI WHERE DATUM=CURRENT_DATE")
        danas = cur.fetchone()[0]
        cur.execute("""SELECT n.BROJ,n.DATUM,k.NAZIV as KLIJENT_NAZIV,n.UREDJAJ,n.DATUM_REALIZACIJE
                       FROM RADNI_NALOZI n LEFT JOIN KLIJENTI k ON n.KLIJENT=k.SIFRA
                       ORDER BY n.BROJ DESC ROWS 10""")
        poslednji = [clean(r) for r in rows_to_dicts(cur)]
    return {"aktivni":aktivni,"realizovani":realizovani,"klijenti":klijenti,"danas":danas,"poslednji":poslednji}

@app.get("/klijenti", tags=["Klijenti"])
def get_klijenti(search: Optional[str]=None, limit: int=300, user=Depends(get_current_user)):
    sql = "SELECT SIFRA,NAZIV,IME,PREZIME,FIRMA_NAZIV,MESTO,ADRESA,TEL_MOBILNI,TEL_FIKSNI,EMAIL,PIB,MB FROM KLIJENTI WHERE 1=1"
    params = []
    if search:
        sql += " AND (UPPER(NAZIV) CONTAINING UPPER(?) OR UPPER(MESTO) CONTAINING UPPER(?) OR TEL_MOBILNI CONTAINING ? OR TEL_FIKSNI CONTAINING ?)"
        params.extend([search,search,search,search])
    sql += f" ORDER BY NAZIV ROWS {limit}"
    with get_db_ctx() as con:
        cur = con.cursor(); cur.execute(sql, params)
        return [clean(r) for r in rows_to_dicts(cur)]

@app.get("/klijenti/{sifra}", tags=["Klijenti"])
def get_klijent(sifra: int, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM KLIJENTI WHERE SIFRA=?", [sifra])
        row = cur.fetchone()
        if not row: raise HTTPException(404, "Klijent nije pronađen")
        result = clean(dict(zip([d[0].lower() for d in cur.description], row)))
        cur.execute("SELECT BROJ,UREDJAJ,DATUM,DATUM_REALIZACIJE FROM RADNI_NALOZI WHERE KLIJENT=? ORDER BY BROJ DESC ROWS 10", [sifra])
        result["nalozi"] = [clean(r) for r in rows_to_dicts(cur)]
    return result

@app.post("/klijenti", tags=["Klijenti"], status_code=201)
def create_klijent(data: KlijentCreate, user=Depends(get_current_user)):
    naziv = data.naziv or (f"{data.ime or ''} {data.prezime or ''}".strip()) or data.firma_naziv or ""
    if not naziv: raise HTTPException(400, "Naziv je obavezan")
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT SIFRA FROM KLIJENTI WHERE UPPER(NAZIV)=UPPER(?) AND UPPER(MESTO)=UPPER(?)",[naziv,data.mesto])
        if cur.fetchone(): raise HTTPException(409, f"Klijent '{naziv}' već postoji u {data.mesto}")
        if data.tel_mobilni:
            tel = data.tel_mobilni.replace(' ','').replace('-','')
            cur.execute("SELECT NAZIV FROM KLIJENTI WHERE TEL_MOBILNI CONTAINING ?",[tel[-7:]])
            dup = cur.fetchone()
            if dup: raise HTTPException(409, f"Telefon već postoji za '{dup[0]}'")
        cur.execute("INSERT INTO KLIJENTI (NAZIV,IME,PREZIME,FIRMA_NAZIV,MESTO,ADRESA,TEL_MOBILNI,TEL_FIKSNI,EMAIL,PIB,MB,NAPOMENA) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [naziv,data.ime,data.prezime,data.firma_naziv,data.mesto,data.adresa,data.tel_mobilni,data.tel_fiksni,data.email,data.pib,data.mb,data.napomena])
        cur.execute("SELECT MAX(SIFRA) FROM KLIJENTI")
        sifra = cur.fetchone()[0]; con.commit()
    return {"status":"created","sifra":sifra}

@app.put("/klijenti/{sifra}", tags=["Klijenti"])
def update_klijent(sifra: int, data: KlijentCreate, user=Depends(get_current_user)):
    naziv = data.naziv or (f"{data.ime or ''} {data.prezime or ''}".strip()) or data.firma_naziv or ""
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("UPDATE KLIJENTI SET NAZIV=?,IME=?,PREZIME=?,FIRMA_NAZIV=?,MESTO=?,ADRESA=?,TEL_MOBILNI=?,TEL_FIKSNI=?,EMAIL=?,PIB=?,MB=?,NAPOMENA=? WHERE SIFRA=?",
                    [naziv,data.ime,data.prezime,data.firma_naziv,data.mesto,data.adresa,data.tel_mobilni,data.tel_fiksni,data.email,data.pib,data.mb,data.napomena,sifra])
        if cur.rowcount==0: raise HTTPException(404,"Klijent nije pronađen")
        con.commit()
    return {"status":"updated"}

@app.get("/nalozi", tags=["Nalozi"])
def get_nalozi(status: Optional[str]=None, search: Optional[str]=None, limit: int=100, user=Depends(get_current_user)):
    sql = """SELECT n.BROJ,n.BARCODE,n.DATUM,n.KLIJENT,k.NAZIV as KLIJENT_NAZIV,
             n.UREDJAJ,n.SERBR,n.GARANCIJA,n.DATUM_REALIZACIJE,n.CENA
             FROM RADNI_NALOZI n LEFT JOIN KLIJENTI k ON n.KLIJENT=k.SIFRA WHERE 1=1"""
    params = []
    if status=="aktivan": sql += " AND n.DATUM_REALIZACIJE IS NULL"
    if status=="zavrsen": sql += " AND n.DATUM_REALIZACIJE IS NOT NULL"
    if search:
        sql += " AND (UPPER(n.UREDJAJ) CONTAINING UPPER(?) OR UPPER(n.SERBR) CONTAINING UPPER(?) OR UPPER(k.NAZIV) CONTAINING UPPER(?) OR CAST(n.BROJ AS VARCHAR(10)) CONTAINING ?)"
        params.extend([search,search,search,search])
    sql += f" ORDER BY n.BROJ DESC ROWS {limit}"
    with get_db_ctx() as con:
        cur = con.cursor(); cur.execute(sql, params)
        return [clean(r) for r in rows_to_dicts(cur)]

@app.get("/nalozi/{broj}", tags=["Nalozi"])
def get_nalog(broj: int, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT n.*,k.NAZIV as KLIJENT_NAZIV,k.TEL_MOBILNI,k.TEL_FIKSNI,k.ADRESA,k.MESTO as K_MESTO FROM RADNI_NALOZI n LEFT JOIN KLIJENTI k ON n.KLIJENT=k.SIFRA WHERE n.BROJ=?",[broj])
        row = cur.fetchone()
        if not row: raise HTTPException(404,"Nalog nije pronađen")
        return clean(dict(zip([d[0].lower() for d in cur.description], row)))

@app.post("/nalozi", tags=["Nalozi"], status_code=201)
def create_nalog(data: NalogCreate, user=Depends(get_current_user)):
    today = date.today()
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT GEN_ID(NALOZI_GEN,1) FROM RDB$DATABASE")
        novi_broj = cur.fetchone()[0]
        barcode = f"RN-{today.year}-{novi_broj:06d}"
        cur.execute("INSERT INTO RADNI_NALOZI (BROJ,BARCODE,DATUM,KLIJENT,UREDJAJ,SERBR,OPIS_KVARA,GARANCIJA,KABLOVI,AMBALAZA,DRAJVERI,OSTALO,OPERATER_ID) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [novi_broj,barcode,today,data.klijent,data.uredjaj,data.serbr,data.opis_kvara,data.garancija,data.kablovi,data.ambalaza,data.drajveri,data.ostalo,user["id"]])
        con.commit()
    return {"status":"created","broj":novi_broj,"barcode":barcode}

@app.put("/nalozi/{broj}", tags=["Nalozi"])
def update_nalog(broj: int, data: NalogCreate, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("UPDATE RADNI_NALOZI SET KLIJENT=?,UREDJAJ=?,SERBR=?,OPIS_KVARA=?,GARANCIJA=?,KABLOVI=?,AMBALAZA=?,DRAJVERI=?,OSTALO=? WHERE BROJ=?",
                    [data.klijent,data.uredjaj,data.serbr,data.opis_kvara,data.garancija,data.kablovi,data.ambalaza,data.drajveri,data.ostalo,broj])
        if cur.rowcount==0: raise HTTPException(404,"Nalog nije pronađen")
        con.commit()
    return {"status":"updated"}

@app.put("/nalozi/{broj}/realizacija", tags=["Nalozi"])
def realizuj_nalog(broj: int, data: RealizacijaData, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("UPDATE RADNI_NALOZI SET IZVRSENI_RADOVI=?,CENA=?,DATUM_REALIZACIJE=CURRENT_DATE WHERE BROJ=?",[data.izvrseni_radovi,data.cena,broj])
        if cur.rowcount==0: raise HTTPException(404,"Nalog nije pronađen")
        con.commit()
    return {"status":"realized"}

@app.get("/nalozi/{broj}/log", tags=["Nalozi"])
def get_log(broj: int, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT ID,NALOG_BROJ,DATUM,OPERATER,STATUS,BELESKA FROM NALOG_LOG WHERE NALOG_BROJ=? ORDER BY DATUM DESC",[broj])
        return [clean(r) for r in rows_to_dicts(cur)]

@app.post("/nalozi/{broj}/log", tags=["Nalozi"])
def add_log(broj: int, data: NalogLogCreate, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("INSERT INTO NALOG_LOG (NALOG_BROJ,OPERATER,STATUS,BELESKA) VALUES (?,?,?,?)",[broj,user["uname"],data.status,data.beleska])
        con.commit()
    return {"status":"created"}

@app.delete("/nalozi/{broj}/log/{log_id}", tags=["Nalozi"])
def delete_log(broj: int, log_id: int, user=Depends(require_admin)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM NALOG_LOG WHERE ID=? AND NALOG_BROJ=?",[log_id,broj])
        con.commit()
    return {"status":"deleted"}

@app.get("/nalozi/{broj}/revers", tags=["Nalozi"])
def stampa_revers(broj: int, token: Optional[str]=None, reklamacija: Optional[int]=0, credentials: HTTPAuthorizationCredentials=Depends(security)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("""SELECT n.BROJ,n.BARCODE,n.DATUM,n.UREDJAJ,n.SERBR,n.GARANCIJA,n.KABLOVI,n.AMBALAZA,n.DRAJVERI,n.OSTALO,n.OPIS_KVARA,n.CENA,n.IZVRSENI_RADOVI,k.NAZIV,k.ADRESA,k.MESTO,k.TEL_MOBILNI,k.TEL_FIKSNI,k.EMAIL FROM RADNI_NALOZI n LEFT JOIN KLIJENTI k ON n.KLIJENT=k.SIFRA WHERE n.BROJ=?""",[broj])
        row = cur.fetchone()
        if not row: raise HTTPException(404,"Nalog nije pronađen")
        cur.execute("SELECT NAZIV,ADRESA,MESTO,PIB,MB,EMAIL,TEL_FIKSNI,TEL_MOBILNI,NAPOMENA_REVERS FROM FIRMA")
        fr = cur.fetchone()
        cur.execute("SELECT DATUM,STATUS,OPERATER,BELESKA FROM NALOG_LOG WHERE NALOG_BROJ=? ORDER BY DATUM ASC",[broj])
        log_rows = cur.fetchall()
        cur.execute("SELECT DATUM FROM NALOG_LOG WHERE NALOG_BROJ=? AND STATUS='Reklamacija' ORDER BY DATUM DESC ROWS 1",[broj])
        rek_row = cur.fetchone()
        datum_reklamacije = rek_row[0].strftime("%d.%m.%Y") if rek_row and hasattr(rek_row[0],"strftime") else None
    f_naziv=fr[0] if fr else "—"; f_pib=fr[3] if fr and fr[3] else "—"; f_mb=fr[4] if fr and fr[4] else "—"
    f_email=fr[5] if fr and fr[5] else "—"; f_tel=(fr[7] or fr[6] or "—") if fr else "—"
    f_napomena=(fr[8] if fr and len(fr) > 8 and fr[8] else "Servisni centar ne odgovara za podatke na uredjaju. Rok za preuzimanje je 45 dana od zavrsetka servisa.")
    # Log popravke - samo za garancijske naloge
    garancija_flag = row[5] if row and len(row) > 5 and row[5] else False
    log_html_garancija = ""
    if garancija_flag and log_rows:
        log_html_garancija = '<div class="section" style="margin-bottom:5px"><div class="section-title" style="color:#16a34a;border-bottom-color:#16a34a30">Log popravke</div><div style="display:flex;flex-wrap:wrap;gap:6px;padding-top:4px">'
        for lr in log_rows:
            if (lr[1] or "").strip() == "Reklamacija":
                continue
            ldatum = lr[0].strftime("%d.%m.%Y %H:%M") if hasattr(lr[0], "strftime") else str(lr[0])[:16]
            lstatus = lr[1] or ""
            loper = lr[2] or ""
            lbeleska = lr[3] or ""
            log_html_garancija += f'<div style="border:1px solid #ddd;border-radius:4px;padding:4px 8px;font-size:9.6px;background:#f9f9f9"><div style="color:#888">{ldatum}</div><div><strong>{lstatus}</strong> &nbsp;<span style="color:#555">{loper}</span></div>'
            if lbeleska:
                log_html_garancija += f'<div style="color:#333;font-size:9px">{lbeleska}</div>'
            log_html_garancija += "</div>"
        log_html_garancija += "</div></div>"
    (br,barcode,datum,uredjaj,serbr,garancija,kablovi,ambalaza,drajveri,ostalo,opis_kvara,cena,izvrseni_radovi,k_naziv,k_adresa,k_mesto,k_mob,k_fix,k_email)=row
    def safe(v,fb="—"):
        if v is None: return fb
        if isinstance(v,(bytes,bytearray)): return fb
        s=str(v).strip(); return s if s else fb
    datum_str=datum.strftime("%d.%m.%Y") if datum else "—"
    cena_str=f"{float(cena):,.2f} RSD".replace(",",".") if cena else "—"
    k_tel_str=" / ".join([x for x in [k_mob,k_fix] if x and str(x).strip()]) or "—"
    opis_str=safe(opis_kvara,"Nije navedeno.")
    import re as _re
    fc=_re.sub(r'\b(d\.?o\.?o\.?|a\.?d\.?|sp\.?|doo|ad|sp)\b','',f_naziv,flags=_re.I).strip()
    rn_prefix=''.join([w[0].upper() for w in fc.split() if w])[:2] or 'RN'
    html=f"""<!DOCTYPE html><html lang="sr"><head><meta charset="UTF-8"><title>Revers {rn_prefix}-{br:04d}</title>
<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@page{{size:A4;margin:8mm 10mm;}}*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Inter',sans-serif;font-size:10px;color:#000;background:#fff;}}
.page{{width:100%;max-width:190mm;margin:0 auto;}}.copy-tag{{display:inline-block;border:1px solid #000;padding:2px 8px;font-size:7.5px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:5px;}}
.header{{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:6px;border-bottom:2px solid #000;margin-bottom:8px;}}
.firma-naziv{{font-size:16px;font-weight:700;}}.firma-info{{font-size:8px;color:#444;margin-top:2px;line-height:1.5;}}
.doc-info{{text-align:right;}}.doc-title{{font-size:18px;font-weight:700;}}.doc-br{{font-size:12px;font-weight:700;margin-top:1px;}}
.doc-datum{{font-size:8px;color:#555;margin-top:2px;}}.gar-badge{{border:1.5px solid #000;font-size:8px;font-weight:700;padding:1px 7px;display:inline-block;margin-top:3px;}}
.gar-badge.ne{{border-style:dashed;color:#555;}}.section{{margin-bottom:6px;}}
.section-title{{font-size:7.5px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;padding-bottom:2px;border-bottom:1px solid #000;margin-bottom:4px;}}
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:3px;}}.info-item{{border:1px solid #999;padding:4px 7px;}}
.info-label{{font-size:7px;color:#555;text-transform:uppercase;margin-bottom:1px;}}.info-val{{font-size:10px;font-weight:600;}}
.info-item.full{{grid-column:1/-1;}}.kvar-box{{border:1px solid #999;border-left:3px solid #000;padding:6px 8px;min-height:28px;}}
.kvar-text{{font-size:10px;line-height:1.5;}}.check-row{{display:flex;gap:14px;flex-wrap:wrap;padding:4px 0;}}
.check-item{{display:flex;align-items:center;gap:5px;font-size:9.5px;}}.check-box{{width:13px;height:13px;border:1.5px solid #000;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;}}
.check-box.checked{{background:#000;color:#fff;}}.napomena{{border:1px solid #999;border-left:3px solid #000;padding:5px 8px;font-size:9.6px;color:#333;line-height:1.5;margin-bottom:8px;}}
.potpisi{{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:10px;padding-top:8px;border-top:1px dashed #999;}}
.potpis-linija{{border-bottom:1.5px solid #000;height:26px;margin-bottom:4px;}}.potpis-label{{font-size:9.6px;color:#555;text-align:center;}}
.footer{{margin-top:5px;padding-top:5px;border-top:1px solid #ccc;display:flex;justify-content:space-between;font-size:9.0px;color:#888;}}
.divider{{border:none;border-top:1px dashed #999;margin:8px 0;position:relative;}}.divider::after{{content:'✂';position:absolute;top:-7px;left:50%;transform:translateX(-50%);background:white;padding:0 6px;font-size:10.8px;color:#999;}}
@media print{{.no-print{{display:none!important;}}body{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}}}</style></head>
<body onload="window.print()">
<div class="no-print" style="padding:6px 12px;background:#f1f3f5;border-bottom:1px solid #ddd;display:flex;gap:8px">
<button onclick="window.print()" style="background:#333;color:#fff;border:none;padding:6px 16px;border-radius:5px;font-size:11px;cursor:pointer">🖨️ Štampaj</button>
<button onclick="window.close()" style="background:#e9ecef;color:#333;border:none;padding:6px 12px;border-radius:5px;font-size:11px;cursor:pointer">✕ Zatvori</button>
</div>
<div class="page">
<div class="copy-tag">Kopija — za servis</div>
<div class="header"><div><div class="firma-naziv">{f_naziv}</div><div class="firma-info">PIB: {f_pib} | MB: {f_mb}</div></div>
<div class="doc-info"><div class="doc-title">RADNI NALOG</div><div style="font-size:8px;color:#888;font-weight:400;letter-spacing:1px">Revers</div><div class="doc-br">{rn_prefix}-{br:04d}</div><div class="doc-datum">Datum: {datum_str}</div>{f'<div style="color:#dc2626;font-weight:700;font-size:9px">⚠ REKLAMACIJA &nbsp;{("· " + datum_reklamacije) if datum_reklamacije else ""}</div>' if reklamacija else ''}
<div class="doc-datum"><span class="gar-badge {'ne' if not garancija else ''}">{'U garanciji' if garancija else 'Van garancije'}</span></div></div></div>
<div class="section"><div class="section-title">Klijent</div><div class="info-grid"><div class="info-item full"><div class="info-label">Naziv / Ime</div><div class="info-val">{safe(k_naziv)} &nbsp;<span style="font-weight:400;color:#555;font-size:10px">{k_tel_str}</span></div></div></div></div>
<div class="section"><div class="section-title">Uređaj</div><div class="info-grid">
<div class="info-item full"><div class="info-label">Naziv / Model</div><div class="info-val">{safe(uredjaj)}</div></div>
<div class="info-item"><div class="info-label">Serijski broj</div><div class="info-val" style="font-family:monospace">{safe(serbr)}</div></div></div></div>
<div class="section"><div class="section-title">Primljeno uz uređaj</div><div class="check-row">
<div class="check-item"><div class="check-box {'checked' if kablovi else ''}">{'✓' if kablovi else ''}</div> Kablovi</div>
<div class="check-item"><div class="check-box {'checked' if ambalaza else ''}">{'✓' if ambalaza else ''}</div> Ambalaža</div>
<div class="check-item"><div class="check-box {'checked' if drajveri else ''}">{'✓' if drajveri else ''}</div> Drajveri</div>
<div class="check-item"><div class="check-box {'checked' if ostalo else ''}">{'✓' if ostalo else ''}</div> Ostalo</div></div></div>
<div class="section"><div class="section-title">Opis kvara</div><div class="kvar-box"><div class="kvar-text">{opis_str}</div></div></div>
{f'<div class="section"><div class="section-title">Izvršeni radovi</div><div class="kvar-box"><div class="kvar-text">{safe(izvrseni_radovi)}</div></div></div>' if izvrseni_radovi else ''}
{log_html_garancija}
<div class="potpisi"><div><div class="potpis-linija"></div><div class="potpis-label">Predao klijent</div></div><div><div class="potpis-linija"></div><div class="potpis-label">Primio serviser</div></div></div>
<div class="footer"><span>Kopija — za servis</span><span>Štampano: {datetime.now().strftime('%d.%m.%Y %H:%M')}</span></div>
<hr class="divider">
<div class="copy-tag">Original — za klijenta</div>
<div class="header"><div><div class="firma-naziv">{f_naziv}</div><div class="firma-info">Tel: {f_tel} | {f_email}</div></div>
<div class="doc-info"><div class="doc-title">REVERS</div><div class="doc-br">{rn_prefix}-{br:04d}</div><div class="doc-datum">Datum: {datum_str}</div>
<div class="doc-datum"><span class="gar-badge {'ne' if not garancija else ''}">{'U garanciji' if garancija else 'Van garancije'}</span></div></div></div>
<div class="info-grid" style="margin-bottom:5px">
<div class="info-item full"><div class="info-label">Naziv / Ime</div><div class="info-val">{safe(k_naziv)}</div></div>
<div class="info-item"><div class="info-label">Telefon</div><div class="info-val">{k_tel_str}</div></div>
<div class="info-item full"><div class="info-label">Uređaj</div><div class="info-val">{safe(uredjaj)}</div></div>
<div class="info-item"><div class="info-label">Serijski broj</div><div class="info-val" style="font-family:monospace">{safe(serbr)}</div></div>
<div class="info-item"><div class="info-label">Cena servisa</div><div class="info-val">{cena_str}</div></div></div>
<div class="napomena">⚠ <strong>Napomena:</strong> {f_napomena}</div>
<div class="potpisi"><div><div class="potpis-linija"></div><div class="potpis-label">Predao klijent</div></div><div><div class="potpis-linija"></div><div class="potpis-label">Primio serviser</div></div></div>
<div class="footer"><span>Original — za klijenta</span><span>{f_naziv}</span><span>Štampano: {datetime.now().strftime('%d.%m.%Y %H:%M')}</span></div>
</div></body></html>"""
    return HTMLResponse(content=html)

@app.get("/istorija", tags=["Istorija"])
def get_istorija(q: str, tip: Optional[str]=None, user=Depends(get_current_user)):
    params=[]
    sql="""SELECT n.BROJ,n.BARCODE,n.DATUM,n.KLIJENT,k.NAZIV as KLIJENT_NAZIV,n.UREDJAJ,n.SERBR,n.OPIS_KVARA,n.IZVRSENI_RADOVI,n.DATUM_REALIZACIJE,n.CENA
           FROM RADNI_NALOZI n LEFT JOIN KLIJENTI k ON n.KLIJENT=k.SIFRA WHERE 1=1"""
    if tip=='serbr': sql+=" AND UPPER(n.SERBR) CONTAINING UPPER(?)"; params.append(q)
    elif tip=='klijent': sql+=" AND UPPER(k.NAZIV) CONTAINING UPPER(?)"; params.append(q)
    else: sql+=" AND (UPPER(n.SERBR) CONTAINING UPPER(?) OR UPPER(k.NAZIV) CONTAINING UPPER(?))"; params.extend([q,q])
    sql+=" ORDER BY n.BROJ DESC ROWS 200"
    with get_db_ctx() as con:
        cur=con.cursor(); cur.execute(sql,params)
        return [clean(r) for r in rows_to_dicts(cur)]

@app.get("/smtp/config", tags=["SMTP"])
def get_smtp(user=Depends(require_admin)):
    with get_db_ctx() as con:
        cur=con.cursor()
        cur.execute("SELECT SMTP_HOST,SMTP_PORT,SMTP_USER,SMTP_PASS,SMTP_FROM,SMTP_TO,SMTP_SSL FROM FIRMA WHERE SIFRA=1")
        row=cur.fetchone()
        if not row: return {}
        return {"smtp_host":decrypt_str(row[0]) if row[0] else "","smtp_port":row[1] or 587,
                "smtp_user":decrypt_str(row[2]) if row[2] else "","smtp_pass":"***" if row[3] else "",
                "smtp_from":decrypt_str(row[4]) if row[4] else "","smtp_to":decrypt_str(row[5]) if row[5] else "","smtp_ssl":row[6] or 0}

@app.put("/smtp/config", tags=["SMTP"])
def save_smtp(data: SmtpConfig, user=Depends(require_admin)):
    with get_db_ctx() as con:
        cur=con.cursor()
        enc_host=encrypt_str(data.smtp_host) if data.smtp_host else None
        enc_user=encrypt_str(data.smtp_user) if data.smtp_user else None
        enc_from=encrypt_str(data.smtp_from) if data.smtp_from else None
        enc_to=encrypt_str(data.smtp_to) if data.smtp_to else None
        if data.smtp_pass and data.smtp_pass!="***":
            cur.execute("UPDATE FIRMA SET SMTP_HOST=?,SMTP_PORT=?,SMTP_USER=?,SMTP_PASS=?,SMTP_FROM=?,SMTP_TO=?,SMTP_SSL=? WHERE SIFRA=1",
                [enc_host,data.smtp_port,enc_user,encrypt_str(data.smtp_pass),enc_from,enc_to,data.smtp_ssl])
        else:
            cur.execute("UPDATE FIRMA SET SMTP_HOST=?,SMTP_PORT=?,SMTP_USER=?,SMTP_FROM=?,SMTP_TO=?,SMTP_SSL=? WHERE SIFRA=1",
                [enc_host,data.smtp_port,enc_user,enc_from,enc_to,data.smtp_ssl])
        con.commit()
    return {"status":"saved"}

@app.post("/smtp/test", tags=["SMTP"])
def test_smtp(user=Depends(require_admin)):
    _send_mail("Test mail — Port Servisni Portal",f"Test uspešno poslat!\n{datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return {"status":"sent"}

def _send_mail(subject: str, body: str, attachments: list = None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.header import Header
    from email import encoders
    with get_db_ctx() as con:
        cur=con.cursor()
        cur.execute("SELECT SMTP_HOST,SMTP_PORT,SMTP_USER,SMTP_PASS,SMTP_FROM,SMTP_TO,SMTP_SSL FROM FIRMA WHERE SIFRA=1")
        row=cur.fetchone()
    if not row or not row[0] or not row[5]: raise HTTPException(400,"SMTP nije podešen")
    host=decrypt_str(row[0]); port=row[1]; smtp_user=decrypt_str(row[2]); smtp_pass=decrypt_str(row[3])
    from_addr=decrypt_str(row[4]); to_addr=decrypt_str(row[5]); use_ssl=row[6]
    # Provjeri da su adrese ispravno dekriptovane
    from_addr = (from_addr or smtp_user or '').strip()
    to_addr   = (to_addr or '').strip()
    if not from_addr or len(from_addr) > 200 or '@' not in from_addr:
        raise HTTPException(500, f"Neispravna From adresa ({len(from_addr)} znakova) - provjerite SMTP podešavanja")
    if not to_addr or len(to_addr) > 500 or '@' not in to_addr:
        raise HTTPException(500, f"Neispravna To adresa ({len(to_addr)} znakova) - provjerite SMTP podešavanja")
    
    msg=MIMEMultipart()
    msg['From'] = from_addr
    msg['To']   = to_addr
    safe_subject = str(subject)[:100].encode('ascii','replace').decode('ascii')
    msg['Subject'] = safe_subject
    msg.attach(MIMEText(body,'plain','utf-8'))
    # Dodaj attachmente
    if attachments:
        for fname, fcontent in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(fcontent)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{fname}"')
            msg.attach(part)
    try:
        if use_ssl: s=smtplib.SMTP_SSL(host,port or 465,timeout=10)
        else: s=smtplib.SMTP(host,port or 587,timeout=10); s.ehlo(); s.starttls(); s.ehlo()
        if smtp_user and smtp_pass: s.login(smtp_user,smtp_pass)
        s.sendmail(from_addr or smtp_user, to_addr.split(','), msg.as_string()); s.quit()
    except smtplib.SMTPAuthenticationError: raise HTTPException(500,"Greška autentifikacije SMTP")
    except Exception as e: raise HTTPException(500,f"Greška pri slanju: {str(e)}")

@app.post("/prijava-problema", tags=["Support"])
def prijavi_problem(data: PrijavaProblema, user=Depends(get_current_user)):
    import urllib.request, urllib.parse
    
    with get_db_ctx() as con:
        cur=con.cursor()
        cur.execute("SELECT NAZIV, EMAIL, TEL_MOBILNI FROM FIRMA WHERE SIFRA=1"); fr=cur.fetchone()
        cur.execute("SELECT NAZIV FROM KORISNICI WHERE SIFRA=1"); op=cur.fetchone()

    firma_naziv   = (fr[0] or "").strip() if fr else ""
    firma_email   = (fr[1] or "").strip() if fr else ""
    firma_mobitel = (fr[2] or "").strip() if fr else ""

    nedostaje = []
    if not firma_naziv or firma_naziv == "Naziv Firme d.o.o.":
        nedostaje.append("naziv firme")
    if not firma_email:
        nedostaje.append("email firme")
    if not firma_mobitel:
        nedostaje.append("mobilni telefon firme")

    if nedostaje:
        raise HTTPException(400, f"Popunite obavezna polja pre slanja prijave: {', '.join(nedostaje)} (Podešavanja → Firma)")

    operater_naziv = (op[0] if op else None) or user["uname"]

    # Pripremi log
    log_content = ""
    logs_dir = os.path.join(_sdir, "logs")
    for log_file in ["server_err.log", "server.log"]:
        log_path = os.path.join(logs_dir, log_file)
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 50*1024))
                    log_content += f"\n=== {log_file} ===\n" + f.read()
            except Exception:
                pass

    payload = json.dumps({
        "api_key":  STANDALONE_KEY,
        "firma":    firma_naziv,
        "email":    firma_email,
        "telefon":  firma_mobitel,
        "verzija":  VERSION,
        "operater": operater_naziv,
        "prioritet": data.prioritet,
        "naslov":   data.naslov,
        "poruka":   data.poruka,
        "log":      log_content[:50000] if log_content else None
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            PRIJAVA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(500, f"Greška pri slanju: {str(e)}")

@app.put("/podesavanja/lozinka", tags=["Podešavanja"])
def promeni_lozinku(data: LozinkaChange, user=Depends(get_current_user)):
    stara_hash=hashlib.sha256(data.stara_lozinka.encode()).hexdigest()
    nova_hash=hashlib.sha256(data.nova_lozinka.encode()).hexdigest()
    if len(data.nova_lozinka)<4: raise HTTPException(400,"Min. 4 karaktera")
    with get_db_ctx() as con:
        cur=con.cursor()
        cur.execute("SELECT PASS FROM KORISNICI WHERE SIFRA=?",[user["id"]]); row=cur.fetchone()
        if not row or row[0]!=stara_hash: raise HTTPException(401,"Pogrešna stara lozinka")
        cur.execute("UPDATE KORISNICI SET PASS=? WHERE SIFRA=?",[nova_hash,user["id"]]); con.commit()
    return {"status":"updated"}

@app.get("/admin/korisnici", tags=["Admin"])
def get_korisnici(user=Depends(require_admin)):
    with get_db_ctx() as con:
        cur=con.cursor(); cur.execute("SELECT SIFRA,UNAME,NAZIV,VRSTA,AKTIVAN FROM KORISNICI ORDER BY NAZIV")
        return [clean(r) for r in rows_to_dicts(cur)]

@app.post("/admin/korisnici", tags=["Admin"], status_code=201)
def create_korisnik(data: KorisnikCreate, user=Depends(require_admin)):
    pass_hash=hashlib.sha256(data.password.encode()).hexdigest()
    with get_db_ctx() as con:
        cur=con.cursor()
        cur.execute("SELECT COUNT(*) FROM KORISNICI WHERE UNAME=?",[data.uname])
        if cur.fetchone()[0]>0: raise HTTPException(409,f"'{data.uname}' već postoji")
        cur.execute("INSERT INTO KORISNICI (UNAME,PASS,NAZIV,VRSTA,AKTIVAN) VALUES (?,?,?,?,1)",[data.uname,pass_hash,data.naziv,data.vrsta])
        cur.execute("SELECT MAX(SIFRA) FROM KORISNICI"); sifra=cur.fetchone()[0]; con.commit()
    return {"status":"created","sifra":sifra}

@app.put("/admin/korisnici/{sifra}/lozinka", tags=["Admin"])
def reset_lozinka(sifra: int, nova_lozinka: str, user=Depends(require_admin)):
    with get_db_ctx() as con:
        cur=con.cursor()
        cur.execute("UPDATE KORISNICI SET PASS=? WHERE SIFRA=?",[hashlib.sha256(nova_lozinka.encode()).hexdigest(),sifra]); con.commit()
    return {"status":"updated"}

@app.put("/admin/korisnici/{sifra}/status", tags=["Admin"])
def toggle_korisnik(sifra: int, aktivan: int, user=Depends(require_admin)):
    with get_db_ctx() as con:
        cur=con.cursor(); cur.execute("UPDATE KORISNICI SET AKTIVAN=? WHERE SIFRA=?",[aktivan,sifra]); con.commit()
    return {"status":"updated"}

@app.get("/check-news", include_in_schema=False)
def check_news():
    """Provjeri novosti sa servera za standalone korisnike."""
    import urllib.request
    NEWS_URL = os.environ.get("NEWS_URL", "https://servisport.rs/updates/standalone_news.json")
    try:
        with urllib.request.urlopen(NEWS_URL, timeout=8) as r:
            data = json.loads(r.read().decode())
        return {
            "news_id": data.get("news_id",""),
            "naslov":  data.get("naslov",""),
            "poruka":  data.get("poruka",""),
            "tip":     data.get("tip","info")
        }
    except Exception:
        return {"news_id": "", "naslov": "", "poruka": "", "tip": "info"}


@app.get("/check-update", include_in_schema=False)
def check_update(user=Depends(require_admin)):
    import urllib.request
    try:
        with urllib.request.urlopen(UPDATE_URL, timeout=8) as r:
            data = json.loads(r.read().decode())
        rv = data.get("version","0.0.0")
        return {"current":VERSION,"latest":rv,"has_update":tuple(int(x) for x in rv.split(".")) > tuple(int(x) for x in VERSION.split(".")),
                "notes":data.get("notes",""),"url":data.get("url","")}
    except Exception as e:
        raise HTTPException(503, f"Ne mogu da proverim: {str(e)}")


@app.post("/do-update", include_in_schema=False)
def do_update(user=Depends(require_admin)):
    import urllib.request, zipfile, shutil, tempfile, threading, platform
    # Dohvati version.json
    try:
        with urllib.request.urlopen(UPDATE_URL, timeout=8) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        raise HTTPException(503, f"Ne mogu da dohvatim update info: {str(e)}")

    zip_url = data.get("url","")
    new_ver  = data.get("version","")
    if not zip_url:
        raise HTTPException(400, "Nema URL-a za download")

    # Preuzmi ZIP
    tmp_dir  = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "update.zip")
    try:
        urllib.request.urlretrieve(zip_url, zip_path)
    except Exception as e:
        raise HTTPException(503, f"Ne mogu da preuzmem update: {str(e)}")

    # Raspakuj i kopiraj fajlove
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for fname in zf.namelist():
                content = zf.read(fname)
                # Kopiraj samo specificne fajlove, ne sve .html iz ZIP-a
                if fname == "server.py":
                    dst = os.path.join(_sdir, "server.py")
                elif fname == "version.txt":
                    dst = os.path.join(_sdir, "version.txt")
                elif fname.endswith(".ico"):
                    dst = os.path.join(_sdir, os.path.basename(fname))
                elif fname.endswith(".bat") and fname != "start_server.bat":
                    dst = os.path.join(_sdir, os.path.basename(fname))
                elif fname == "index.html":
                    dst = os.path.join(STATIC_DIR, "index.html")
                elif fname == "changelog.html":
                    dst = os.path.join(STATIC_DIR, "changelog.html")
                elif fname == "html/index.html":
                    dst = os.path.join(STATIC_DIR, "index.html")
                elif fname == "html/changelog.html":
                    dst = os.path.join(STATIC_DIR, "changelog.html")
                else:
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, 'wb') as f:
                    f.write(content)
    except Exception as e:
        raise HTTPException(500, f"Greška pri raspakivanju: {str(e)}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Restartuj servis ili proces
    def restart():
        import time, subprocess
        time.sleep(3)  # Brzi restart
        if platform.system() == "Windows":
            # Osvjezi Desktop precicu sa novom ikonicom
            try:
                bat_path = os.path.join(_sdir, "update_shortcut.bat")
                if os.path.exists(bat_path):
                    subprocess.Popen(["cmd", "/c", bat_path],
                                   capture_output=True, shell=False)
            except:
                pass
            subprocess.Popen(["schtasks", "/end", "/tn", "PortServisniPortal"], 
                           capture_output=True, shell=False)
            time.sleep(2)
            subprocess.Popen(["schtasks", "/run", "/tn", "PortServisniPortal"],
                           capture_output=True, shell=False)
        else:
            subprocess.Popen(["sudo","systemctl","restart","servisni-portal"])

    threading.Thread(target=restart, daemon=True).start()
    return {"status": "updating", "version": new_ver}


# ─── BACKUP & RESTORE ─────────────────────────────────────────────────────────


@app.put("/nalozi/{broj}/reklamacija", tags=["Nalozi"])
def reklamacija_nalog(broj: int, user=Depends(get_current_user)):
    with get_db_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT DATUM_REALIZACIJE, GARANCIJA FROM RADNI_NALOZI WHERE BROJ=?", [broj])
        row = cur.fetchone()
        if not row: raise HTTPException(404, "Nalog nije pronadjen")
        if not row[0]: raise HTTPException(400, "Nalog nije realizovan")
        garancija = row[1]
        cur.execute("UPDATE RADNI_NALOZI SET DATUM_REALIZACIJE=NULL WHERE BROJ=?", [broj])
        cur.execute("DELETE FROM NALOG_LOG WHERE NALOG_BROJ=? AND STATUS != 'Reklamacija'", [broj])
        cur.execute("INSERT INTO NALOG_LOG (NALOG_BROJ, DATUM, STATUS, OPERATER, BELESKA) VALUES (?, CURRENT_TIMESTAMP, 'Reklamacija', ?, 'Nalog vracen u aktivne')", [broj, user["uname"]])
        con.commit()
        return {"status": "reklamacija", "garancija": bool(garancija)}

@app.get("/backup", include_in_schema=False)
def backup_db(user=Depends(require_admin)):
    """Preuzmi backup baze kao fajl."""
    import shutil, io
    from fastapi.responses import StreamingResponse
    
    backup_path = os.path.join(_sdir, "db", "backup", 
                               f"servis_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gdb")
    
    try:
        shutil.copy2(DB_PATH, backup_path)
        
        def iterfile():
            with open(backup_path, 'rb') as f:
                yield from f
        
        fname = os.path.basename(backup_path)
        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={fname}"}
        )
    except Exception as e:
        raise HTTPException(500, f"Greška pri backup-u: {str(e)}")


@app.get("/backup/lista", include_in_schema=False)
def backup_lista(user=Depends(require_admin)):
    """Lista svih backup fajlova."""
    backup_dir = os.path.join(_sdir, "db", "backup")
    os.makedirs(backup_dir, exist_ok=True)
    fajlovi = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.endswith('.gdb'):
            fp = os.path.join(backup_dir, f)
            size = os.path.getsize(fp)
            mtime = datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%d.%m.%Y %H:%M')
            fajlovi.append({"naziv": f, "velicina": f"{size//1024} KB", "datum": mtime})
    return fajlovi


@app.post("/restore", include_in_schema=False)
async def restore_db(file: bytes = None, user=Depends(require_admin)):
    """Restore baze iz uploadovanog fajl."""
    from fastapi import UploadFile, File
    raise HTTPException(400, "Koristite /restore/upload endpoint")


from fastapi import UploadFile, File

@app.post("/restore/upload", include_in_schema=False)
async def restore_upload(file: UploadFile = File(...), user=Depends(require_admin)):
    """Restore baze iz uploadovanog .gdb fajla."""
    if not file.filename.endswith('.gdb'):
        raise HTTPException(400, "Fajl mora biti .gdb")
    
    # Sačuvaj backup pre restore-a
    backup_path = os.path.join(_sdir, "db", "backup",
                               f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gdb")
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    
    # Zatvori sve konekcije i zameni bazu
    content = await file.read()
    tmp_path = DB_PATH + ".tmp"
    
    try:
        with open(tmp_path, 'wb') as f:
            f.write(content)
        
        # Zameni bazu
        os.replace(tmp_path, DB_PATH)
        return {"status": "restored", "backup": os.path.basename(backup_path)}
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(500, f"Greška pri restore-u: {str(e)}")


@app.get("/restore/preuzmi/{naziv}", include_in_schema=False)
def preuzmi_backup(naziv: str, user=Depends(require_admin)):
    """Preuzmi backup fajl."""
    from fastapi.responses import StreamingResponse
    # Validacija - samo .gdb fajlovi iz backup foldera
    if '/' in naziv or '\\' in naziv or not naziv.endswith('.gdb'):
        raise HTTPException(400, "Neispravan naziv")
    
    path = os.path.join(_sdir, "db", "backup", naziv)
    if not os.path.exists(path):
        raise HTTPException(404, "Fajl nije pronađen")
    
    def iterfile():
        with open(path, 'rb') as f:
            yield from f
    
    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={naziv}"}
    )

if __name__ == "__main__":
    import uvicorn, platform, sys
    if _sdir not in sys.path: sys.path.insert(0,_sdir)
    if platform.system()=="Windows":
        _fb=os.path.join(_sdir,"fbclient.dll")
        if os.path.exists(_fb) and _USE_DRIVER:
            from firebird.driver import driver_config
            driver_config.fb_client_library.value=_fb
        os.environ.setdefault("FIREBIRD",_sdir)
        import subprocess as _sp
        _sp.run(["powershell","-Command","Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],capture_output=True)
    print("="*55)
    print(f"  Port Servisni Portal — Standalone v{VERSION}")
    print(f"  Baza: {DB_PATH}")
    print(f"  HTTP: http://0.0.0.0:8080")
    print("="*55)
    ensure_db()
    config=uvicorn.Config(app,host="0.0.0.0",port=8080,reload=False)
    uvicorn.Server(config).run()
