"""Generatorul eșantionului fictiv de test (80 de pagini, firmă inventată).

Eșantionul are cazuri plantate cu răspunsul corect cunoscut (expected.json):
grupuri de pagini despre aceeași procedură, conflicte de valori, pași lipsă sau
inversați, pagini învechite, duplicate, traduceri RO→EN, pagini-capcană cu titluri
asemănătoare și pagini unice. Rezultatul e determinist pentru același seed.

Toate numele, adresele și valorile sunt inventate (domeniul example.test).
"""

from __future__ import annotations

import hashlib
import json
import random
import struct
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .model import (
    IMAGES_DIR,
    Block,
    ImageRef,
    Manifest,
    Page,
    Source,
    write_dataset,
)

DEFAULT_SEED = 20261027
EXTRACTED_AT = "2026-10-27T12:00:00Z"

NOTEBOOKS = {
    "Proceduri IT": ["Rețea", "Conturi", "Software", "Hardware", "Securitate"],
    "Suport Clienți": ["Ghiduri", "Întrebări frecvente", "Diverse"],
    "Operațiuni": ["Administrativ", "Resurse umane", "Facilități", "Note"],
}

STALE_NOTE = "Notă: varianta veche, nu mai folosiți după migrarea din 2021."

INTROS = [
    "Procedura de mai jos se aplică tuturor angajaților.",
    "Pași verificați de echipa IT.",
    "Ghid rapid, pas cu pas.",
    "Actualizat după ultima schimbare de sistem.",
]


@dataclass
class Procedure:
    key: str
    title: str
    notebook: str
    section: str
    steps: list[str]
    slots: dict[str, str]
    conflict: tuple[str, str] | None = None  # (slot, valoare diferită)
    old: dict[str, str] = field(default_factory=dict)  # valorile din varianta învechită
    en: tuple[str, list[str]] | None = None  # (titlu, pași) pentru traducere


PROCEDURES: list[Procedure] = [
    Procedure(
        "vpn", "Instalare client VPN", "Proceduri IT", "Rețea",
        [
            "Descarcă clientul VPN versiunea {ver} de pe portal.example.test/software.",
            "Rulează instalarea ca utilizator standard și acceptă setările implicite.",
            "La „Server”, completează {host}.",
            "Setează portul {port} și protocolul TLS.",
            "Autentifică-te cu contul de domeniu și codul din aplicația de autentificare.",
            "Verifică în colțul din dreapta jos că pictograma VPN e verde.",
        ],
        {"ver": "5.2", "host": "vpn.example.test", "port": "443"},
        conflict=("port", "8443"), old={"ver": "4.1"},
    ),
    Procedure(
        "parola", "Resetare parolă cont de domeniu", "Proceduri IT", "Conturi",
        [
            "Deschide portalul parole.example.test.",
            "Alege „Am uitat parola” și introdu numele de utilizator.",
            "Confirmă identitatea prin codul trimis pe telefonul de serviciu.",
            "Alege o parolă nouă de minimum {minlen} caractere.",
            "Parola expiră după {days} zile; primești un e-mail cu 7 zile înainte.",
            "Deconectează-te și reconectează-te pe toate dispozitivele.",
        ],
        {"minlen": "12", "days": "90"},
        conflict=("minlen", "14"), old={"days": "60"},
    ),
    Procedure(
        "imprimanta", "Adăugare imprimantă de rețea", "Proceduri IT", "Hardware",
        [
            "Deschide Setări > Dispozitive > Imprimante.",
            "Alege „Adaugă imprimantă”, apoi „Imprimanta dorită nu e listată”.",
            "Introdu calea {path}.",
            "Instalează driverul {driver} când ești întrebat.",
            "Tipărește o pagină de test.",
        ],
        {"path": r"\\print01.example.test\Etaj2", "driver": "PCL6 v3.4"},
        conflict=("path", r"\\print02.example.test\Etaj2"), old={"driver": "PCL5 v1.9"},
    ),
    Procedure(
        "backup", "Backup zilnic al bazei de date de test", "Operațiuni", "Administrativ",
        [
            "Conectează-te la serverul {host}.",
            "Oprește serviciul aplicației cu comanda {stop}.",
            "Rulează scriptul {script}.",
            "Copiază arhiva în {path}.",
            "Pornește serviciul și verifică jurnalul.",
        ],
        {"host": "db-test.example.test", "stop": "net stop AplicatieTest",
         "script": "backup_v2.ps1", "path": r"D:\Backup\Zilnic"},
        conflict=("path", r"E:\Backup"), old={"script": "backup_v1.bat"},
    ),
    Procedure(
        "cont_nou", "Creare cont utilizator nou", "Proceduri IT", "Conturi",
        [
            "Primește formularul aprobat de manager.",
            "Creează contul în consola de administrare, în formatul prenume.nume.",
            "Adaugă utilizatorul în grupul {group}.",
            "Setează cota de stocare la {quota} GB.",
            "Trimite datele de logare prin canalul securizat, nu pe e-mail.",
        ],
        {"group": "GRP-Standard", "quota": "50"},
        conflict=("quota", "100"), old={"group": "GRP-Users"},
    ),
    Procedure(
        "certificat", "Reînnoire certificat SSL pentru serverul web", "Proceduri IT", "Securitate",
        [
            "Generează cererea CSR cu cheie de {keylen} biți.",
            "Trimite CSR-ul la autoritatea internă prin pki.example.test.",
            "Descarcă certificatul și lanțul intermediar.",
            "Instalează certificatul pe {host} și repornește serviciul web.",
            "Verifică data de expirare cu comanda {cmd}.",
        ],
        {"keylen": "2048", "host": "web01.example.test",
         "cmd": "openssl x509 -noout -enddate -in server.crt"},
        conflict=("keylen", "4096"), old={"cmd": "certutil -dump server.crt"},
        en=("Renew the SSL certificate for the web server", [
            "Generate the CSR with a {keylen}-bit key.",
            "Send the CSR to the internal authority via pki.example.test.",
            "Download the certificate and the intermediate chain.",
            "Install the certificate on {host} and restart the web service.",
            "Check the expiry date with the command {cmd}.",
        ]),
    ),
    Procedure(
        "email_mobil", "Configurare e-mail pe telefon", "Suport Clienți", "Ghiduri",
        [
            "Instalează aplicația de e-mail din magazinul companiei.",
            "Introdu adresa în formatul nume@example.test.",
            "La server, completează {host}.",
            "Acceptă politica de securitate (PIN de minimum {pin} cifre).",
            "Sincronizează și trimite un e-mail de test.",
        ],
        {"host": "mail.example.test", "pin": "6"},
        conflict=("pin", "4"), old={"host": "mail-old.example.test"},
        en=("Set up e-mail on your phone", [
            "Install the e-mail app from the company store.",
            "Enter your address in the format name@example.test.",
            "For the server, enter {host}.",
            "Accept the security policy (PIN of at least {pin} digits).",
            "Sync and send a test e-mail.",
        ]),
    ),
    Procedure(
        "concediu", "Solicitare concediu de odihnă", "Operațiuni", "Resurse umane",
        [
            "Deschide aplicația HR la hr.example.test.",
            "Alege „Cerere nouă” > „Concediu de odihnă”.",
            "Completează perioada cu cel puțin {notice} zile lucrătoare înainte.",
            "Trimite cererea către managerul direct.",
            "După aprobare, setează răspunsul automat în e-mail.",
        ],
        {"notice": "5"},
        conflict=("notice", "10"),
        en=("Request annual leave", [
            "Open the HR app at hr.example.test.",
            "Choose “New request” > “Annual leave”.",
            "Fill in the period at least {notice} working days in advance.",
            "Send the request to your direct manager.",
            "After approval, set the automatic reply in your e-mail.",
        ]),
    ),
    Procedure(
        "predare_laptop", "Predare laptop la plecarea din firmă", "Operațiuni", "Administrativ",
        [
            "Salvează datele personale pe un stick propriu; datele de serviciu rămân pe {share}.",
            "Deconectează-te de la toate conturile.",
            "Completează formularul de predare {form}.",
            "Predă laptopul, încărcătorul și ecusonul la IT, camera {room}.",
            "Primește confirmarea semnată.",
        ],
        {"share": r"\\files.example.test\Echipe", "form": "F-27", "room": "104"},
        conflict=("room", "210"), old={"form": "F-12"},
    ),
    Procedure(
        "incident", "Raportare incident de securitate", "Proceduri IT", "Securitate",
        [
            "Deconectează calculatorul de la rețea, dar nu-l opri.",
            "Sună la numărul intern {phone}.",
            "Trimite detaliile la {mail}.",
            "Notează ora, ce ai văzut și ce ai apăsat.",
            "Așteaptă instrucțiunile echipei de securitate.",
        ],
        {"phone": "5555", "mail": "securitate@example.test"},
        conflict=("phone", "5000"), old={"mail": "securitate-vechi@example.test"},
    ),
    Procedure(
        "software", "Instalare aplicație din catalogul intern", "Proceduri IT", "Software",
        [
            "Deschide Centrul de software.",
            "Caută aplicația {app}.",
            "Apasă „Instalează” și așteaptă aproximativ {minutes} minute.",
            "Repornește calculatorul dacă ți se cere.",
            "Verifică versiunea în meniul Ajutor > Despre.",
        ],
        {"app": "EditorExemplu", "minutes": "10"},
        conflict=("minutes", "20"),
    ),
    Procedure(
        "parcare", "Solicitare card de acces în parcare", "Operațiuni", "Facilități",
        [
            "Completează cererea în portalul facilitati.example.test.",
            "Atașează copia talonului mașinii.",
            "Alege nivelul {level}.",
            "Ridică cardul de la recepție după {days} zile lucrătoare.",
            "Semnează procesul-verbal de predare.",
        ],
        {"level": "-1", "days": "3"},
        conflict=("level", "-2"),
    ),
    Procedure(
        "sedinta", "Programare ședință online", "Suport Clienți", "Ghiduri",
        [
            "Deschide calendarul din aplicația de e-mail.",
            "Alege „Ședință nouă” și adaugă participanții.",
            "Bifează opțiunea de întâlnire online.",
            "Activează camera de așteptare pentru invitații externi.",
            "Trimite invitația cu agenda atașată.",
        ],
        {},
    ),
    Procedure(
        "arhivare_mail", "Arhivare e-mailuri vechi", "Suport Clienți", "Întrebări frecvente",
        [
            "Deschide Fișier > Instrumente > Curățare cutie poștală.",
            "Alege „Arhivează elementele mai vechi de {months} luni”.",
            "Selectează folderul de arhivă de pe {share}.",
            "Pornește arhivarea și nu închide aplicația.",
            "Verifică dimensiunea cutiei poștale după finalizare.",
        ],
        {"months": "12", "share": r"\\files.example.test\ArhivaMail"},
    ),
    Procedure(
        "periferic", "Înlocuire monitor sau periferic defect", "Proceduri IT", "Hardware",
        [
            "Deschide un tichet la helpdesk.example.test.",
            "Alege categoria „Hardware > Periferice”.",
            "Descrie defectul și atașează o fotografie.",
            "Așteaptă confirmarea și programarea înlocuirii.",
            "Predă echipamentul defect la IT.",
        ],
        {},
    ),
]

# Mărimea fiecărui grup (în ordinea din PROCEDURES), fără duplicate și traduceri.
GROUP_SIZES = [4, 4, 4, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2]
CONFLICT_GROUPS = set(range(12))  # varianta 1 schimbă o valoare
STALE_GROUPS = set(range(10))  # ultima variantă e învechită
STALE_WITH_NOTE = {1, 4, 7}
STEP_DIFF = {  # grup -> (varianta, tip)
    9: (2, "missing_step"), 10: (2, "reordered"), 11: (2, "reordered"),
    12: (1, "missing_step"), 13: (1, "reordered"), 14: (1, "missing_step"),
}
DUPLICATE_OF = [0, 1, 2, 3, 4]  # copie aproape identică a paginii de bază
TRANSLATED = [5, 6, 7]  # traducere EN a paginii de bază

# Pagini-capcană: titlu sau vocabular apropiat de o procedură, dar altă procedură.
DISTRACTORS: list[tuple[str, str, str, list[str]]] = [
    ("Instalare imprimantă locală USB", "Proceduri IT", "Hardware", [
        "Conectează cablul USB la laptop.",
        "Așteaptă ca Windows să găsească dispozitivul.",
        "Dacă nu e găsit, instalează driverul de pe stick-ul primit cu imprimanta.",
        "Setează imprimanta ca implicită doar dacă o folosești zilnic.",
    ]),
    ("Dezactivare cont utilizator la plecare", "Proceduri IT", "Conturi", [
        "Primește notificarea de plecare de la HR.",
        "Blochează autentificarea în ultima zi de lucru, la ora 18.",
        "Mută căsuța de e-mail în modul partajat pentru 30 de zile.",
        "Șterge licențele alocate după confirmarea managerului.",
    ]),
    ("Restaurare bază de date de test din backup", "Operațiuni", "Administrativ", [
        "Anunță echipa că mediul de test va fi indisponibil o oră.",
        "Alege arhiva dorită după dată.",
        "Rulează scriptul de restaurare și urmărește progresul.",
        "Compară numărul de înregistrări cu raportul din ziua respectivă.",
    ]),
    ("Reînnoire abonament software de proiectare", "Proceduri IT", "Software", [
        "Verifică cu 30 de zile înainte câte licențe sunt folosite.",
        "Cere oferta prin departamentul de achiziții.",
        "Aprobă comanda în aplicația de achiziții.",
        "Actualizează lista de licențe din registrul intern.",
    ]),
    ("Configurare semnătură e-mail", "Suport Clienți", "Ghiduri", [
        "Deschide Setări > E-mail > Semnătură.",
        "Folosește modelul cu numele, funcția și telefonul de birou.",
        "Nu adăuga imagini mari sau citate.",
        "Salvează și trimite-ți un e-mail de verificare.",
    ]),
    ("Solicitare zi liberă pentru donare de sânge", "Operațiuni", "Resurse umane", [
        "Păstrează adeverința primită la centrul de transfuzii.",
        "Încarcă adeverința în dosarul tău din aplicația HR.",
        "Ziua liberă se ia în cel mult o săptămână de la donare.",
        "Managerul primește automat o notificare.",
    ]),
    ("Predare echipamente între colegi", "Operațiuni", "Administrativ", [
        "Notează seria echipamentului de pe eticheta din spate.",
        "Completați amândoi procesul-verbal de transfer.",
        "Trimiteți procesul-verbal scanat la inventar.",
        "Actualizați responsabilul în registrul de echipamente.",
    ]),
    ("Raportare defect în clădire (apă, curent)", "Operațiuni", "Facilități", [
        "Pentru urgențe, sună la recepție.",
        "Pentru restul, deschide o cerere în portalul de facilități.",
        "Indică etajul, camera și o fotografie a problemei.",
        "Urmărește starea cererii în portal.",
    ]),
    ("Instalare fonturi suplimentare", "Proceduri IT", "Software", [
        "Descarcă fontul doar din biblioteca aprobată.",
        "Deschide fișierul și apasă „Instalează pentru utilizatorul curent”.",
        "Repornește aplicațiile Office ca fontul să apară.",
        "Nu trimite documente cu fonturi neaprobate către clienți.",
    ]),
    ("Rezervare sală de ședințe", "Operațiuni", "Facilități", [
        "Caută sala în lista de resurse din calendar.",
        "Verifică numărul de locuri și echipamentul video.",
        "Adaugă sala ca participant la invitație.",
        "Eliberează rezervarea dacă ședința se anulează.",
    ]),
]

# Pagini unice, fără pereche: nu trebuie să apară în niciun grup.
UNIQUE: list[tuple[str, str, str, list[str]]] = [
    ("Program de lucru în perioada sărbătorilor", "Operațiuni", "Note", [
        "Între sărbători biroul e deschis între 9 și 15.",
        "Serviciul de suport funcționează cu o echipă redusă.",
    ]),
    ("Glosar de termeni interni", "Suport Clienți", "Diverse", [
        "Tichet: cererea înregistrată de un client.",
        "Escaladare: transferul unei cereri la nivelul următor.",
        "SLA: timpul maxim de răspuns convenit.",
    ]),
    ("Reguli pentru bucătăria comună", "Operațiuni", "Facilități", [
        "Spală vasele imediat după folosire.",
        "Frigiderul se golește în fiecare vineri la ora 16.",
    ]),
    ("Idei pentru activitatea de echipă din primăvară", "Operațiuni", "Note", [
        "Drumeție de o zi în apropierea orașului.",
        "Atelier de gătit sau de olărit.",
        "Turneu de jocuri de societate.",
    ]),
    ("Prescurtări folosite în rapoarte", "Suport Clienți", "Diverse", [
        "TR: timp de rezolvare.",
        "NC: neconformitate.",
        "PV: proces-verbal.",
    ]),
    ("Note: prezentarea produsului Exemplu Pro", "Suport Clienți", "Diverse", [
        "Prezentarea a durat 40 de minute și a avut 25 de participanți.",
        "Întrebările principale au fost despre prețuri și integrare.",
    ]),
    ("Program de curățenie pe etaje", "Operațiuni", "Facilități", [
        "Etajele 1 și 2 se curăță dimineața, etajul 3 după-amiaza.",
        "Lasă birourile libere de hârtii vineri seara.",
    ]),
    ("Recomandări de ergonomie la birou", "Operațiuni", "Resurse umane", [
        "Marginea de sus a monitorului la nivelul ochilor.",
        "O pauză scurtă la fiecare oră.",
        "Scaunul reglat astfel încât picioarele să stea pe podea.",
    ]),
    ("Ghid de stil pentru prezentări", "Suport Clienți", "Diverse", [
        "Folosește șablonul cu fundal alb și logo-ul în colțul din dreapta jos.",
        "Maximum șase rânduri de text pe un slide.",
    ]),
    ("Bun venit în echipă", "Operațiuni", "Resurse umane", [
        "În prima săptămână ai un coleg care te ajută cu întrebările.",
        "Programul de instruire începe în a doua zi.",
    ]),
    ("Întrebări frecvente despre tichetele de masă", "Operațiuni", "Resurse umane", [
        "Cardul se încarcă în prima zi lucrătoare a lunii.",
        "Pierderea cardului se anunță la HR.",
    ]),
    ("Calendar instruiri în trimestrul 1", "Operațiuni", "Note", [
        "Ianuarie: securitatea informației.",
        "Februarie: comunicare cu clienții.",
        "Martie: prim ajutor.",
    ]),
    ("Lucrul de acasă: rezumatul regulilor", "Operațiuni", "Resurse umane", [
        "Maximum două zile pe săptămână, stabilite cu managerul.",
        "Conexiunea trebuie să fie stabilă pentru ședințele video.",
    ]),
    ("Checklist pentru deplasări de serviciu", "Operațiuni", "Administrativ", [
        "Aprobarea deplasării înainte de rezervări.",
        "Păstrează toate bonurile pentru decont.",
        "Decontul se depune în cel mult 5 zile de la întoarcere.",
    ]),
    ("Contacte utile (fictive)", "Suport Clienți", "Diverse", [
        "Recepție: interior 100.",
        "Facilități: facilitati@example.test.",
    ]),
]


# ---------- imagini PNG minimale, fără biblioteci externe ----------

def _png(rgb: tuple[int, int, int], size: int = 8, mark: int = 0) -> bytes:
    rows = b""
    for y in range(size):
        row = b"\x00"
        for x in range(size):
            row += bytes(rgb) if (x + y + mark) % 5 else b"\xff\xff\xff"
        rows += row

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


# ---------- construirea paginilor ----------

@dataclass
class _Draft:
    role: str
    title: str
    notebook: str
    section: str
    intro: str
    steps: list[str]
    note: str
    created: datetime
    modified: datetime
    group: str | None = None
    values: dict[str, str] = field(default_factory=dict)
    step_diff: tuple[str, list[int]] | None = None
    image: str | None = None
    key: str = ""


def _date(rng: random.Random, start: str, end: str) -> datetime:
    a = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    b = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    span = int((b - a).total_seconds() // 60)
    return a + timedelta(minutes=rng.randrange(span))


def _created_before(rng: random.Random, modified: datetime) -> datetime:
    return modified - timedelta(days=rng.randrange(1, 400), minutes=rng.randrange(600))


def _other_location(rng: random.Random, notebook: str, section: str) -> tuple[str, str]:
    while True:
        nb = rng.choice(sorted(NOTEBOOKS))
        sec = rng.choice(NOTEBOOKS[nb])
        if (nb, sec) != (notebook, section):
            return nb, sec


def _fmt(steps: list[str], values: dict[str, str]) -> list[str]:
    return [s.format(**values) for s in steps]


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:00Z")


def build_sample(seed: int = DEFAULT_SEED) -> tuple[Manifest, list[Page], dict[str, bytes], dict]:
    """Construiește eșantionul în memorie: (manifest, pagini, imagini, expected)."""
    rng = random.Random(seed)
    drafts: list[_Draft] = []
    title_forms = ["{t}", "{t} (actualizat)", "Ghid: {tl}", "{t}, pe pași"]

    for gi, proc in enumerate(PROCEDURES):
        base_values = dict(proc.slots)
        for vi in range(GROUP_SIZES[gi]):
            values = dict(base_values)
            role, note = "variant", ""
            steps = list(proc.steps)
            step_diff = None
            stale = gi in STALE_GROUPS and vi == GROUP_SIZES[gi] - 1
            if vi == 0:
                role = "base"
                nb, sec = proc.notebook, proc.section
                modified = _date(rng, "2025-01-10", "2026-09-30")
            else:
                nb, sec = _other_location(rng, proc.notebook, proc.section)
                modified = _date(rng, "2024-02-01", "2026-09-30")
            if vi == 1 and gi in CONFLICT_GROUPS and proc.conflict:
                slot, alt = proc.conflict
                values[slot] = alt
                role = "conflict"
            if gi in STEP_DIFF and STEP_DIFF[gi][0] == vi:
                kind = STEP_DIFF[gi][1]
                if kind == "missing_step":
                    del steps[2]
                    step_diff = (kind, [2])
                else:
                    steps[1], steps[2] = steps[2], steps[1]
                    step_diff = (kind, [1, 2])
            if stale:
                values.update(proc.old)
                modified = _date(rng, "2019-03-01", "2021-06-30")
                role = "stale"
                if gi in STALE_WITH_NOTE or not proc.old:
                    note = STALE_NOTE
            title = title_forms[vi % len(title_forms)].format(t=proc.title, tl=proc.title.lower())
            drafts.append(_Draft(
                role=role, title=title, notebook=nb, section=sec,
                intro=INTROS[(gi + vi) % len(INTROS)], steps=_fmt(steps, values), note=note,
                created=_created_before(rng, modified), modified=modified,
                group=proc.key, step_diff=step_diff, key=f"{proc.key}#{vi}",
                # doar valorile care apar efectiv în pașii rămași
                values={k: v for k, v in values.items() if any("{" + k + "}" in s for s in steps)},
            ))

    bases = {d.group: d for d in drafts if d.role == "base"}

    for gi in DUPLICATE_OF:
        b = bases[PROCEDURES[gi].key]
        nb, sec = _other_location(rng, b.notebook, b.section)
        steps = [s.rstrip(".") for s in b.steps]  # aceeași procedură, punctuație puțin diferită
        modified = b.modified + timedelta(days=rng.randrange(1, 20))
        drafts.append(_Draft(
            role="duplicate", title=f"{b.title} (copie)", notebook=nb, section=sec,
            intro=b.intro, steps=steps, note="", created=modified - timedelta(days=1),
            modified=modified, group=b.group, values=dict(b.values), key=f"{b.group}#dup",
        ))

    for gi in TRANSLATED:
        proc = PROCEDURES[gi]
        b = bases[proc.key]
        assert proc.en is not None
        title_en, steps_en = proc.en
        modified = _date(rng, "2025-01-10", "2026-09-30")
        drafts.append(_Draft(
            role="translation", title=title_en, notebook="Suport Clienți", section="Ghiduri",
            intro="Step-by-step guide.", steps=_fmt(steps_en, b.values), note="",
            created=_created_before(rng, modified), modified=modified,
            group=proc.key, values=dict(b.values), key=f"{proc.key}#en",
        ))

    for i, (title, nb, sec, steps) in enumerate(DISTRACTORS):
        modified = _date(rng, "2023-01-01", "2026-09-30")
        drafts.append(_Draft(
            role="distractor", title=title, notebook=nb, section=sec, intro=INTROS[i % len(INTROS)],
            steps=list(steps), note="", created=_created_before(rng, modified), modified=modified,
            key=f"distractor#{i}",
        ))

    for i, (title, nb, sec, paras) in enumerate(UNIQUE):
        modified = _date(rng, "2022-01-01", "2026-09-30")
        drafts.append(_Draft(
            role="unique", title=title, notebook=nb, section=sec, intro="", steps=list(paras),
            note="", created=_created_before(rng, modified), modified=modified, key=f"unique#{i}",
        ))

    # Imagini: 3 imagini folosite pe câte 2 pagini (6 pagini), plus 2 imagini unice.
    images: dict[str, bytes] = {}
    def add_image(data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        images[sha] = data
        return sha

    by_key = {d.key: d for d in drafts}
    shared = [
        (add_image(_png((30, 90, 200))), ["vpn#0", "vpn#1"]),  # în același grup
        (add_image(_png((200, 60, 40))), ["imprimanta#0", "distractor#0"]),  # între pagini diferite
        (add_image(_png((40, 160, 80))), ["cont_nou#0", "unique#9"]),
    ]
    for sha, keys in shared:
        for k in keys:
            by_key[k].image = sha
    by_key["backup#0"].image = add_image(_png((120, 120, 120), mark=1))
    by_key["unique#3"].image = add_image(_png((220, 180, 30), mark=2))

    # Ordine amestecată, ca grupurile să nu fie una după alta, apoi id-uri stabile.
    rng.shuffle(drafts)
    ids = {d.key: f"sample-p{n:03d}" for n, d in enumerate(drafts, start=1)}

    pages: list[Page] = []
    for d in drafts:
        blocks: list[Block] = []
        lines: list[str] = []
        if d.intro:
            blocks.append(Block("para", d.intro))
            lines.append(d.intro)
        if d.role == "unique":
            for p in d.steps:
                blocks.append(Block("para", p))
                lines.append(p)
        else:
            for n, s in enumerate(d.steps, start=1):
                blocks.append(Block("list_item", s, level=1))
                lines.append(f"{n}. {s}")
        if d.note:
            blocks.append(Block("para", d.note))
            lines.append(d.note)
        pages.append(Page(
            id=ids[d.key], notebook=d.notebook, section_path=[d.section], title=d.title,
            created=_iso(d.created), modified=_iso(d.modified), text="\n".join(lines), blocks=blocks,
            images=[ImageRef(sha256=d.image, alt="Captură de ecran (fictivă)")] if d.image else [],
            source=Source(kind="sample", ref=f"sample:{ids[d.key]}"),  # fără indicii despre răspuns
        ))

    expected = _expected(drafts, ids, shared, seed)

    sections: dict[str, set[str]] = {}
    for p in pages:
        sections.setdefault(p.notebook, set()).add(p.section_path[0])
    manifest = Manifest(
        source=Source(kind="sample", ref=f"docaudit.sample seed={seed}"),
        extracted_at=EXTRACTED_AT,
        notebooks=[{"name": nb, "sections": sorted(secs)} for nb, secs in sorted(sections.items())],
        selection={"notebooks": sorted(sections), "sections": [], "pages": []},
        page_count=len(pages),
        note="Eșantion fictiv generat automat. Nu conține date reale.",
    )
    return manifest, pages, images, expected


def _expected(drafts: list[_Draft], ids: dict[str, str], shared: list[tuple[str, list[str]]], seed: int) -> dict:
    groups, conflicts, step_diffs = [], [], []
    for proc in PROCEDURES:
        members = [d for d in drafts if d.group == proc.key]
        core = sorted(ids[d.key] for d in members if d.role != "translation")
        trans = sorted(ids[d.key] for d in members if d.role == "translation")
        groups.append({"key": proc.key, "title": proc.title, "pages": core, "translation_pages": trans})
        for slot in sorted(proc.slots):
            values = {ids[d.key]: d.values[slot] for d in sorted(members, key=lambda d: ids[d.key])
                      if slot in d.values}
            if len(set(values.values())) > 1:
                conflicts.append({"group": proc.key, "slot": slot, "values": values})
        for d in members:
            if d.step_diff:
                step_diffs.append({"group": proc.key, "page": ids[d.key],
                                   "kind": d.step_diff[0], "steps": d.step_diff[1]})

    def pick(role: str) -> list[str]:
        return sorted(ids[d.key] for d in drafts if d.role == role)

    bases = {d.group: ids[d.key] for d in drafts if d.role == "base"}
    return {
        "schema_version": 1,
        "seed": seed,
        "page_count": len(drafts),
        "groups": groups,
        "conflicts": conflicts,
        "step_diffs": sorted(step_diffs, key=lambda s: s["page"]),
        "stale": pick("stale"),
        "duplicates": sorted([sorted([bases[d.group], ids[d.key]]) for d in drafts if d.role == "duplicate"]),
        "translations": sorted([[bases[d.group], ids[d.key]] for d in drafts if d.role == "translation"]),
        "distractors": pick("distractor"),
        "ungrouped": sorted(pick("distractor") + pick("unique")),
        "image_duplicates": {sha: sorted(ids[k] for k in keys) for sha, keys in shared},
        "targets": {
            "grouping_pairwise_f1_min": 0.85,
            "grouping_pairwise_f1_min_with_embeddings": 0.90,
            "conflict_recall_min": 0.80,
            "conflict_false_alarm_max": 0.10,
            "stale_found_min": 8,
            "max_seconds_cpu": 60,
            "max_seconds_cpu_without_embeddings": 15,
        },
    }


def write_sample(folder: Path, seed: int = DEFAULT_SEED) -> int:
    """Scrie eșantionul în folder (format normalizat + expected.json). Întoarce nr. de pagini."""
    manifest, pages, images, expected = build_sample(seed)
    write_dataset(folder, manifest, pages)
    img_dir = folder / IMAGES_DIR
    img_dir.mkdir(exist_ok=True)
    for sha, data in sorted(images.items()):
        (img_dir / f"{sha}.png").write_bytes(data)
    (folder / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return len(pages)
