# DocAudit — Plan Etapa 1

Status: **aprobat (27.10.2026)**. Etapele 2–3 făcute; Etapa 3 de verificat pe OneNote real.

## 1. Pe scurt

DocAudit citește unul sau mai multe notebook-uri OneNote alese de tine, găsește paginile care descriu aceeași procedură, le compară și îți arată conflictele și paginile probabil învechite. **Tu decizi** pentru fiecare: păstrez, marchez învechită, arhivez, ignor. Nimic nu se scrie în OneNote până nu apeși „Aplică” și confirmi previzualizarea. Totul rulează pe laptop, fără să trimită conținut în afară.

```
OneNote (desktop)          DocAudit (local, 127.0.0.1)
┌──────────────┐  COM   ┌───────────┐  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐
│ Notebook A,B │──────▶│ 1 Extrage │─▶│ 2 Metadate │─▶│ 3 Grupare│─▶│ 4 Compară│─▶│ 5 Raport +  │
│ (doar citire)│        │ (selecție)│  │ + normal.  │  │ asemănare│  │ pe grup  │  │   decizii   │
└──────────────┘        └───────────┘  └────────────┘  └──────────┘  └──────────┘  └──────┬──────┘
       ▲                                                                                │
       └──────────── 6 Aplică (doar la cererea ta: dry-run → backup → mută în Arhivă) ◀──┘
```

## 2. Arhitectura în pași

### Pas 1 — Extragere și selecție
- **Sursa principală: API-ul COM al OneNote desktop** (`pywin32`, `OneNote.Application`). `GetHierarchy` dă lista de notebook-uri → grupuri de secțiuni → secțiuni → pagini; `GetPageContent` dă XML-ul paginii (titlu, date, text, imagini în base64). Totul local, fără cont sau internet.
- **Selecție**: în UI vezi arborele notebook → secțiune → pagină cu bife. Poți alege notebook-uri întregi, secțiuni sau pagini individuale, și poți exclude secțiuni permanent (ex. „Personal”, „Arhivă”). Selecția se salvează ca **profil** („Proceduri IT”, „Doar Rețea”) ca s-o refolosești.
- **Incremental**: la a doua rulare se extrag doar paginile cu `lastModifiedTime` schimbat.
- **Surse alternative** (dacă COM e blocat): folder cu exporturi manuale pe secțiune (.docx / .pdf / .mht) sau Microsoft Graph (vezi secț. 4, oprit implicit).
- Rezultatul: formatul normalizat din secțiunea 3, scris în `data/<profil>/`.

### Pas 2 — Metadate și normalizare
Pentru fiecare pagină:
- curățare text (spații, bullet-uri, tabele → rânduri), limbă detectată (ro/en);
- **pași de procedură**: listele numerotate și liniile imperative devin o listă ordonată de pași;
- **entități „valori”**: versiuni (`v2.3`, `build 1045`), căi (`C:\…`, `\\server\…`), URL-uri, comenzi, porturi, IP-uri, nume de aplicații, date menționate în text. Acestea sunt ce se compară la conflicte;
- imagini: hash exact (SHA-256) + hash perceptual (aceeași captură, redimensionată); OCR local cu Tesseract — **opțional**, oprit implicit;
- semnale de vechime: data modificării, cuvinte ca „vechi”, „nu mai folosiți”, „deprecated”, versiuni mai mici decât cele din alte pagini.

### Pas 3 — Grupare după asemănare
Scop: „paginile astea descriu aceeași procedură”. Trei semnale combinate, cu ponderi configurabile:
1. **Titlu** — asemănare fuzzy (`rapidfuzz`), ex. „Instalare VPN” ≈ „VPN – instalare (nou)”.
2. **Text lexical** — TF-IDF pe n-grame de caractere (merge bine pe ro/en amestecat, fără diacritice) + MinHash pentru copii aproape identice.
3. **Sens (opțional)** — embeddings locale multilingve (`sentence-transformers`, model mic ~120 MB, pe CPU), prinde traduceri RO↔EN și reformulări.

Scor combinat → graf de pagini legate peste un prag → grupuri (componente conexe + tăiere a legăturilor slabe). Pragul se reglează din UI cu previzualizare live („la 0.70 ai 14 grupuri”).
Tu poți: **uni** două grupuri, **scoate** o pagină din grup („nu e aceeași procedură”), **fixa** o pagină într-un grup. Corecturile tale se păstrează la rulările următoare.

### Pas 4 — Comparare pe grupuri
Pentru fiecare grup, perechi de pagini față în față:
- **aliniere pe pași** (diff pe lista de pași, nu pe text brut) → pași lipsă, pași în plus, ordine diferită;
- **conflicte de valori**: același „loc” cu valori diferite (port 443 vs 8443, cale diferită, versiune diferită, comandă diferită);
- **duplicate**: conținut aproape identic → candidat la arhivare;
- **învechire**: pagina e mai veche ȘI conținutul ei e cuprins/înlocuit de alta mai nouă, sau are versiuni mai mici, sau cuvinte de tip „deprecated”;
- **conflicte de sens (opțional)**: LLM local prin Ollama, doar pe perechi deja suspecte, oprit implicit.

Fiecare constatare are: tip, severitate (mare / medie / mică), dovada (fragmentele din ambele pagini, evidențiate), și o **sugestie** („pagina B pare versiunea curentă”). Sugestia nu e aplicată niciodată singură.

### Pas 5 — Raport și decizii
- **UI** (vezi secț. 5) cu lista de grupuri ordonată după severitate.
- **Decizii posibile per pagină**: ✅ Referință (versiunea bună) · ⚠️ Marchează învechită · 📦 Arhivează · 🙈 Ignoră constatarea · ✂️ Nu face parte din grup · 📝 Notă pentru mine.
- Deciziile se scriu într-un **jurnal** local (SQLite): cine, când, ce, de ce. Se pot anula oricând înainte de „Aplică”.
- **Export raport**: HTML (de citit/printat), CSV (pentru Excel), Markdown.

### Pas 6 — Aplică (doar la cererea ta)
- Ecran **„De aplicat”**: lista deciziilor neaplicate, cu previzualizare exactă („pagina X se mută din Rețea în Arhivă”).
- La confirmare: **copie de siguranță** a XML-ului paginii în `backups/`, apoi:
  - **Arhivează** → pagina ajunge în secțiunea **„Arhivă”** (nume configurabil) a aceluiași notebook, cu o linie la început: „Mutat din: <secțiune>, <dată>, motiv: <motiv>”. Originalul ajunge în Coșul OneNote (recuperabil), nu e șters definitiv.
  - **Marchează învechită** → prefix în titlu „[ÎNVECHIT]” și/sau tag OneNote, pagina rămâne pe loc.
- **Restaurare** din Arhivă înapoi în secțiunea originală, din același ecran.
- Opțiune globală „mod doar citire” (implicit **pornit** până activezi tu scrierea).

## 3. Formatul de intrare (normalizat)

Indiferent de sursă (COM, exporturi, Graph), totul ajunge în același format, ca analiza să nu depindă de sursă:

```
data/<profil>/
  manifest.json          # schema_version, sursa, data extragerii, notebook-uri, selecția
  pages.jsonl            # o pagină pe linie
  images/<sha256>.png    # imaginile, deduplicate după hash
```

O pagină în `pages.jsonl`:
```json
{
  "schema_version": 1,
  "id": "{onenote-page-id}",
  "notebook": "Proceduri IT",
  "section_path": ["Rețea", "VPN"],
  "title": "Instalare client VPN",
  "created": "2023-04-11T09:12:00Z",
  "modified": "2025-02-03T14:40:00Z",
  "author": "opțional",
  "text": "text curat, cu paragrafe",
  "blocks": [{"type": "heading|para|list_item|table_row", "level": 1, "text": "..."}],
  "images": [{"sha256": "…", "phash": "…", "alt": "", "ocr_text": null}],
  "attachments": [{"name": "config.xml", "sha256": "…"}],
  "links": ["onenote:…", "https://…"],
  "source": {"kind": "onenote_com", "ref": "…"}
}
```
Câmpul `schema_version` permite schimbări viitoare fără să stricăm datele vechi.

## 4. Ce rulează local și ce nu

| Componentă | Unde | Rețea? |
|---|---|---|
| Extragere COM, analiză, grupare, comparare, raport | laptop | **niciuna** |
| UI (FastAPI + HTMX, fără build) | laptop, doar `127.0.0.1` | niciuna |
| Jurnal decizii, backup-uri | laptop (`data/`, `backups/`) | niciuna |
| Embeddings / Tesseract / Ollama (opționale) | laptop, CPU | **doar la instalare** (descărcare model), apoi offline forțat (`HF_HUB_OFFLINE=1`) |
| Microsoft Graph (alternativă la COM) | cloud-ul Microsoft al companiei | **da** — oprit implicit, doar dacă alegi explicit |
| GitHub | doar cod și date **fictive** | niciodată conținut real |
| Claude | doar cod și eșantion fictiv | niciodată conținut real |

Garanții verificate prin teste: niciun apel de rețea în timpul analizei (test cu socket blocat), serverul refuză conexiuni din afara `127.0.0.1`, fără telemetrie.

## 5. Interfața (minimalistă)

Aplicație web locală, deschisă din iconița din tray (`pythonw`, fără .exe). Temă luminoasă/întunecată, ro/en, scurtături de tastatură. Cinci ecrane:

1. **Sursă** — arborele notebook-urilor cu bife, profiluri salvate, „Extrage”.
2. **Analiză** — progres, praguri (glisoare), ce module opționale sunt pornite.
3. **Grupuri** — stânga: lista grupurilor (culoare după severitate, filtre: conflicte / învechite / duplicate / nerezolvate). Dreapta: paginile grupului **una lângă alta**, diferențele evidențiate, butoanele de decizie sub fiecare pagină. Tastele `J/K` navighează, `R/O/A/I` decid.
4. **De aplicat** — deciziile în așteptare, previzualizare, „Aplică” cu confirmare.
5. **Arhivă și jurnal** — ce s-a arhivat/marcat, de către cine, când, cu „Restaurează”.

Setări: pragurile, ponderile semnalelor, numele secțiunii de arhivă, prefixul „[ÎNVECHIT]”, secțiuni excluse, module opționale, limbă, mod doar citire.

## 6. Testul pe eșantion (50–100 pagini, fără date sensibile)

**Eșantion fictiv generat**, cu seed fix, pentru o firmă inventată („Exemplu SRL”, adrese `example.test`): **80 de pagini în 3 notebook-uri**:

| Caz plantat | Pagini | Ce trebuie să găsească |
|---|---|---|
| 15 proceduri, fiecare în 2–4 variante | ~45 | 15 grupuri corecte |
| … din care cu conflicte de valori (port, cale, versiune, comandă) | 12 grupuri | conflictul exact, cu fragmentele |
| … cu pași lipsă / ordine diferită | 6 grupuri | pașii diferiți |
| Pagini învechite (dată veche + versiune mică / „nu mai folosiți”) | 10 | marcate „probabil învechită” |
| Duplicate aproape identice | 5 perechi | marcate duplicat |
| Perechi traduse RO↔EN | 3 | grupate doar cu embeddings pornite |
| Pagini unice (fără pereche) | 15 | **nu** apar în niciun grup |
| Imagini duplicate între pagini | 6 | recunoscute după hash |

Fișierul `expected.json` conține răspunsurile corecte. Testul automat măsoară:
- grupare: F1 pe perechi **≥ 0.85** (≥ 0.90 cu embeddings);
- conflicte găsite: **≥ 80%** din cele plantate, cu cel mult 10% alarme false;
- învechite: **≥ 8 din 10**;
- **zero scrieri** în sursă (hash-ul fișierelor de intrare identic înainte/după);
- **zero apeluri de rețea**;
- durată: **< 60 s** pentru 80 pagini pe CPU (fără embeddings < 15 s).

Pe Windows, același eșantion se importă într-un **notebook OneNote de test** (creat de script prin COM), ca să verificăm cap-coadă extragerea și mutarea în Arhivă + restaurarea, fără să atingem notebook-urile reale.

## 7. Etapele următoare (după „da”)

| Etapa | Ce | Livrabil testabil |
|---|---|---|
| 2 | Schelet proiect, format normalizat, generator eșantion + `expected.json`, teste „fără rețea / fără scriere” | `pytest` verde pe validarea formatului |
| 3 | Extragere COM + selecție + import din exporturi manuale | eșantionul trece prin COM pe un notebook de test |
| 4 | Metadate + grupare | F1 grupare pe eșantion |
| 5 | Comparare + învechire | scorurile conflicte/învechite |
| 6 | UI + jurnal decizii + export raport | flux complet fără scriere în OneNote |
| 7 | Aplică: arhivare/marcare cu dry-run, backup, restaurare | test cap-coadă pe notebook de test |
| 8 | Tray, setări, i18n, integrare DevPilot (`devpilot.tool.json`) | pornire cu `pythonw` |

**Stack propus**: Python 3.12, `pywin32`, FastAPI + Uvicorn, HTMX + CSS simplu (fără build JS), SQLite, `scikit-learn`, `rapidfuzz`, `datasketch`, `pystray`; opționale: `sentence-transformers`, `pytesseract`, Ollama.
