# CHANGELOG — DocAudit

## 0.1.1 — 2026-10-28
- Reparat: `Install.bat` se oprea la „Creez iconita si scurtaturile” cu `UnicodeEncodeError` (cp1252). Pe Windows, ieșirea redirecționată nu putea scrie diacriticele din mesaje („Iconiță”). Acum DocAudit scrie mereu în UTF-8, iar `Install.bat` setează și `PYTHONIOENCODING=utf-8`. Găsit de Bogdan la prima instalare (Python 3.14).
- Teste: 109 trecute.
- Livrare: `git pull`, apoi din nou `Install.bat`.

## 0.1.0 — 2026-10-27
- Etapa 6: interfață în browser, doar pe 127.0.0.1, cu șase ecrane: Sursă (bife pe notebook / secțiune / pagină), Analiză (prag cu tabel pe praguri), Grupuri (constatări + paginile una lângă alta, valorile diferite evidențiate, taste J/K, 1–9, R/O/A/I), De aplicat, Arhivă și jurnal, Setări. RO / EN / DE, temă luminoasă și întunecată.
- Serverul folosește doar biblioteca standard Python, nu FastAPI, ca instalarea să nu depindă de pachete pe care IT-ul le-ar putea bloca. Protecții: verificarea Host, un jeton pe fiecare cerere /api/, CSP strict și niciun CORS. Textul paginilor intră în pagină doar ca text.
- Jurnalul deciziilor în `decisions.db` (SQLite local, lângă date): Referință, Învechită, Arhivează, Lasă așa, Ignoră constatarea, Nu e în grup (scrie și corectura de grupare), Notă. Fiecare decizie se poate anula până la aplicare.
- Raport HTML, CSV (cu `;` și BOM, pentru Excel) și Markdown, din interfață sau cu `report`.
- Etapa 7: „Aplică”, cu previzualizare exactă, doar pentru deciziile bifate și doar cu „Permite scrierea în OneNote” pornit în setări (oprit implicit). Înainte de fiecare pagină se salvează XML-ul ei în `_backups`. Arhivarea = copie în secțiunea „Arhivă” a aceluiași notebook, cu nota „Mutat din: <secțiune>, <dată>, motiv: <motiv>”; originalul ajunge în Coșul OneNote. „Învechită” = prefixul „[ÎNVECHIT] ” în titlu. O pagină modificată în OneNote după extragere se sare. „Restaurează” întoarce pagina în secțiunea ei sau scoate prefixul.
- Pe eșantion, scrierea merge într-un OneNote fals (`demo_onenote.json`), ca fluxul complet să se poată încerca fără OneNote.
- Etapa 8: `pythonw -m docaudit` pornește iconița din tray (Deschide / Închide) și browserul; o a doua pornire doar deschide browserul. Iconița e desenată din cod (.png / .ico), fără fișiere binare în repo. `Install.bat` creează scurtăturile DocAudit pe Desktop și în meniul Start. Setări în `settings.json`. Descriere pentru DevPilot în `devpilot.tool.json`.
- Comenzi noi: `ui`, `report`, `apply` (previzualizare; `--yes` aplică), `restore`, `make-icon`; fără comandă pornește aplicația.
- Teste: 108 trecute (`pytest -q`, Linux, Python 3.13), inclusiv serverul (Host, jeton, Origin, căi) și arhivare + marcare + restaurare pe OneNote-ul fals.
- Livrare: `git pull`, apoi **din nou `Install.bat`** (adaugă pystray / Pillow și scurtăturile).

## 0.0.6 — 2026-10-27
- Etapa 5: compararea paginilor din fiecare grup, local și doar citire. Comanda `compare` scrie `findings.json` lângă date și nu modifică paginile, grupurile sau OneNote.
- Pașii se aliniază între pagini chiar dacă sunt reformulați: valorile (cifre, căi, adrese, coduri ca GRP-Users, opțiuni de comandă) sunt înlocuite cu un semn comun înainte de comparare.
- Constatări: conflicte de valori (cu valoarea fiecărei pagini), pași lipsă, pași în plus, pași în altă ordine, duplicate aproape identice și aceeași imagine pe mai multe pagini.
- Pagini probabil învechite, cu motivul afișat: „nu mai folosiți” / „deprecated” / „veraltet” în text, versiune mai mică (4.1 față de 5.2, backup_v1 față de backup_v2), valoare în minoritate pe o pagină mult mai veche, sau pagina e cu peste 3 ani mai veche decât cea mai nouă din grup.
- Pentru fiecare grup, o pagină sugerată ca versiunea curentă: nu e învechită și are cele mai multe valori comune cu restul. Sugestia nu se aplică.
- Paginile în altă limbă decât restul grupului (de exemplu o traducere DE) nu se compară pas cu pas, ca să nu apară pași „lipsă” falși.
- Rezultate pe eșantion: conflicte 20/20, alarme false 0%, învechite 10/10, diferențe de pași 6/6, duplicate 5/5, sub o secundă.
- Teste: 94 trecute (`pytest -q`, Linux, Python 3.13).
- Livrare: comenzi noi `compare` și `compare-eval`; `git pull`, apoi `DocAudit.bat compare demo`.

## 0.0.5 — 2026-10-27
- Instalare fără admin pe Windows: `Install.bat` creează mediul Python în `%LOCALAPPDATA%\DocAudit\venv`, iar `Install.bat semantic` adaugă și modelul pentru asemănarea după sens. Comenzile se rulează cu `DocAudit.bat <comandă>`. De ce: testul nu trebuie să ceară pași de Python făcuți de mână.
- Datele extrase stau implicit în `%LOCALAPPDATA%\DocAudit\data`, nu în folderul repo-ului din Google Drive, ca documentația companiei să nu se sincronizeze în Drive. În comenzi se poate scrie doar numele extragerii (de exemplu `group demo`).
- Suport pentru documentație în română, engleză și germană: detectarea limbii, cuvinte germane ignorate în titluri (Anleitung, neu, aktualisiert, Kopie…) și semne de pagină învechită în toate trei limbile (veraltet, nicht mehr verwenden, deprecated, nu mai folosiți…). Interfața are acum și germană.
- Eșantionul are o traducere RO→DE (în locul uneia EN) și 2 pagini unice în germană; numărul de pagini și cazurile rămân aceleași.
- Comandă nouă `download-model`: singura care folosește internetul, o singură dată.
- `docs/INSTALARE.md` înlocuiește `docs/TESTARE_WINDOWS.md`: instalare, test rapid fără OneNote, test pe un notebook de test, test opțional pe un notebook real.
- Teste: 84 trecute (`pytest -q`, Linux, Python 3.13).
- Livrare: `git pull`, apoi dublu clic pe `Install.bat`.

## 0.0.4 — 2026-10-27
- Etapa 4: gruparea paginilor care descriu aceeași procedură, local și fără biblioteci externe. Scorul combină textul (TF-IDF pe n-grame de caractere, 70%) cu titlul curățat de cuvinte ca „ghid”, „actualizat” sau „copie” (30%). Perechile candidate se găsesc printr-un index, nu fiecare cu fiecare.
- Grupurile se formează de la perechea cea mai asemănătoare în jos, peste un prag (implicit 0.6). `--scan` arată câte grupuri ies la fiecare prag.
- Corecturile tale se păstrează între rulări: „unește” două pagini, „scoate din grup” o pagină (ea nu se mai leagă de paginile acelui grup).
- Asemănare după sens, opțională (`pip install -e .[semantic]`, model multilingv local, rețeaua blocată la încărcare): poate doar ridica scorul, de exemplu pentru traduceri RO↔EN.
- Eșantionul are acum variante reformulate (alte verbe, note în plus); fixture-ul a fost regenerat, cazurile plantate sunt aceleași.
- Rezultate: pe eșantion F1 1.00 (precizie 1.00, acoperire 1.00) la orice prag între 0.4 și 0.7. Paginile-capcană și traducerile rămân negrupate, cum era de așteptat fără sens. 2000 de pagini sintetice se compară în ~9 s.
- Teste: 72 trecute (`pytest -q`, Linux, Python 3.13).
- Livrare: comenzi noi `group`, `group-eval`, `group-merge`, `group-detach`; nimic de reinstalat în afară de `pip install -e .`.

## 0.0.3 — 2026-10-27
- Etapa 3: extragerea din OneNote desktop prin COM, strict doar citire (`ReadOnlyOneNote` expune doar GetHierarchy și GetPageContent). De ce: paginile alese ajung în formatul v1 fără ca DocAudit să poată modifica ceva în OneNote.
- Parser XML OneNote 2013: grupuri de secțiuni, Coșul de reciclare ignorat, titluri (h1–h6), liste numerotate și cu buline (pe niveluri), tabele, imagini (base64, OCR-ul OneNote), linkuri, fișiere atașate, contururi în ordinea de citire.
- Selecție prin bife (notebook / secțiune / pagină), secțiunea „Arhivă” exclusă implicit, profiluri salvate în `data/profiles/`.
- Extragere incrementală: paginile cu aceeași dată de modificare nu se mai cer din OneNote; imaginile nefolosite se curăță din cache-ul DocAudit.
- Alternativă fără COM: import din exporturi manuale .mht și .docx (datele sunt ale fișierelor).
- Comenzi noi: `tree`, `extract`, `profile`, `import-files`, `make-test-notebook` (Windows, doar folder nou), `check-sample`; `--demo` rulează totul pe eșantion, fără OneNote.
- Imaginile se salvează cu extensia lor (`images/<sha256>.<ext>`), nu doar .png; câmpurile din schema v1 nu s-au schimbat.
- OneNote Extractor din NexusX nu e refolosit: citește .onepkg euristic, fără titluri și date sigure.
- Teste: 59 trecute (`pytest -q`, Linux, Python 3.13), CI pe Ubuntu + Windows. Netestat pe OneNote real: pașii sunt în `docs/TESTARE_WINDOWS.md`.
- Livrare: pe Windows `pip install -e .[dev,windows]`.

## 0.0.2 — 2026-10-27
- Etapa 2: schelet Python (`pyproject.toml`, pachetul `docaudit`, CLI `sample` / `validate`), formatul normalizat v1 cu validare, i18n RO/EN. De ce: toate etapele următoare citesc același format, indiferent de sursă.
- Eșantion fictiv de 80 de pagini în 3 notebook-uri, cu `expected.json`: 15 grupuri, 20 de conflicte de valori în 12 grupuri, 6 grupuri cu pași lipsă/inversați, 10 pagini învechite, 5 duplicate, 3 traduceri RO→EN, 10 pagini-capcană, 15 pagini unice, 3 imagini duplicate pe 6 pagini.
- Garanții testate: niciun apel de rețea (`no_network`), nicio scriere în folderul analizat (`tree_digest`), server doar pe loopback (`is_loopback`).
- Decizii: proiectul și repo-ul se numesc DocAudit (repo redenumit din DocPilot), pe GitHub-ul personal (KNOWN_ISSUES 4 și 5 închise).
- Teste: 30 trecute (`pytest -q`) local pe Linux (Python 3.13) și în CI pe Ubuntu + Windows (Python 3.11, 3.12).
- Livrare: doar cod nou, nimic de instalat pentru utilizator încă.

## 0.0.1 — 2026-10-27
- Etapa 1: planul de arhitectură (`docs/PLAN.md`), CLAUDE.md, KNOWN_ISSUES.md, CHANGELOG.md după șabloanele dev-framework. De ce: fixăm formatul de intrare, regulile „doar local” și „fără ștergeri automate” înainte de cod.
- Teste: nu există încă (fără cod). Testul pe eșantionul de 50–100 pagini e descris în plan, se implementează la Etapa 2.
- Livrare: doar documentație.
