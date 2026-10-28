# CHANGELOG — DocAudit

## 0.1.7 — 2026-10-28
- Reparat: pe laptopul de lucru OneNote cădea la **fiecare** citire de pagină prin pywin32 (lista de notebook-uri mergea), iar DocAudit îl repornea la fiecare pagină, deci fereastra „How do you want to start OneNote?” apărea mereu. Acum, dacă o cale de citire face OneNote să cadă înainte de prima pagină reușită, DocAudit trece la următoarea: **PowerShell** (ca scriptul vechi de export), apoi comtypes, apoi legarea dinamică. Calea care merge și cea care face OneNote să cadă se țin minte în `data\onenote_read.json`, ca rularea următoare să nu mai provoace căderea. Dacă toate căile fac OneNote să cadă, extragerea se oprește la prima pagină, cu un mesaj clar.
- Logul arată acum și de ce n-au mers variantele de legătură dinainte (de exemplu „OneNote.Application”) și pe ce cale se citesc paginile.
- „Oprește” și oprirea după 3 minute închid și procesul PowerShell pornit de extragere.
- Teste: 141 trecute (`pytest -q`, Linux), inclusiv trecerea la altă cale după o cădere, ținerea minte între rulări și oprirea când toate căile cad.
- Livrare: `git pull`, apoi din nou `Install.bat`; închide întâi DocAudit din iconița de lângă ceas.

## 0.1.6 — 2026-10-28
- Reparat: când OneNote se bloca la o pagină (de exemplu cu fereastra „How do you want to start OneNote?” după o cădere), DocAudit rămânea „ocupat” („rulează o extragere…”), iar „Extrage” și „Oprește” nu mai făceau nimic până la închiderea aplicației. Acum extragerea din interfață rulează într-un **proces separat** (`extract/worker.py`), pe care DocAudit îl supraveghează: dacă nu avansează 3 minute la aceeași pagină, îl oprește și spune la ce pagină s-a blocat; „Oprește” îl închide după 20 de secunde dacă nu se oprește singur. Interfața rămâne liberă.
- Ce s-a citit se salvează acum la fiecare 20 de pagini (înainte 50), deci după o oprire forțată se pierde puțin.
- Teste: 136 trecute (`pytest -q`, Linux), inclusiv OneNote „înghețat” la pagina 26 (oprire după timp, reluare de la pagina 20) și „Oprește” pe un proces blocat.
- Livrare: `git pull`, apoi din nou `Install.bat`; închide întâi DocAudit din iconița de lângă ceas.

## 0.1.5 — 2026-10-28
- Reparat: pe laptopul de lucru (1449 de pagini) extragerea se oprea la primele pagini cu „The RPC server is unavailable” (0x800706BA): OneNote se închidea sau se bloca la cererea unei pagini, iar DocAudit continua cu același obiect COM mort. Acum, când OneNote nu mai răspunde, DocAudit nu mai încearcă alte variante de parametri, se reconectează (pornește OneNote din nou) și reîncearcă pagina; dacă OneNote cade din nou la aceeași pagină, o cere fără imagini și notează asta în log. Când OneNote e doar ocupat (sincronizare), așteaptă și reîncearcă. Între pagini e o pauză de 50 ms, ca în scriptul vechi.
- Reparat: copia logului din Google Drive rămânea la pornire, pentru că Drive nu urcă un fișier ținut deschis. Acum fiecare rând se scrie și fișierul se închide imediat (local și în Drive).
- Teste: 134 trecute (`pytest -q`, Linux, Python 3.13), inclusiv OneNote care cade o dată (reconectare) și care cade doar cu imaginile (pagina fără imagini).
- Livrare: `git pull`, apoi din nou `Install.bat`; închide întâi DocAudit din iconița de lângă ceas.

## 0.1.4 — 2026-10-28
- Reparat: extragerea dădea **0 pagini** fără explicație (raportat de Bogdan pe laptopul de lucru, notebook de 700+ pagini). Cauza: cu legătura din biblioteca de tipuri OneNote (varianta din 0.1.3), parametrul de ieșire al lui `GetPageContent` nu se dă deloc, iar a doua încercare trimitea parametrii mutați, deci fiecare pagină pica. Acum fiecare apel COM încearcă variantele de parametri în ordinea corectă și o ține minte pe cea care merge (`extract/connect.py`, `ComCaller`).
- Reparat: „De aplicat” arăta `TypeError: IApplication.GetHierarchy() takes from 1 to 4 positional arguments but 5 were given`. Scrierea folosește aceeași legătură; la scrieri se încearcă altă variantă doar când numărul de parametri e greșit, ca o scriere să nu se repete.
- Reparat: „Analiză” rămânea la „Analizez…” când apărea o eroare (de exemplu asemănarea după sens fără model). Eroarea rămâne acum în pagină; caseta „Asemănare după sens” e inactivă dacă modelul nu e instalat; o extragere cu 0 pagini nu mai poate fi analizată și spune de ce.
- Nou: extragerea rulează **în fundal**, cu „Pagina N din M”, butonul „Oprește” și ultimele rânduri din log. Se salvează la fiecare 50 de pagini, deci o extragere oprită continuă de unde a rămas. Dacă primele 5 pagini pică toate, se oprește singură cu eroarea.
- Nou: **logul tehnic** (Setări → Log tehnic): pornire, versiune, legătura cu OneNote, câte pagini și secțiuni, durate, erori cu locul din cod. Local în `data\logs\docaudit.log` și copie în `logs\pc-xxxxxx.log` din clona DocAudit din Google Drive, ca să-l pot citi de pe alt laptop (se oprește din Setări). Fără titluri, nume de notebook-uri sau text din pagini; căile din folderul utilizatorului devin `~`, numele de utilizator e ascuns.
- „Verifică legătura cu OneNote” are un rând nou: **Citirea unei pagini** (cazul de mai sus se vedea doar așa).
- Din „1. Updating Script” (scriptul vechi de export): preluate deocamdată logul pe pagină și oprirea clară la erori; restul (export PDF, duplicate exacte, documente pentru bot) e propus separat.
- Teste: 131 trecute (`pytest -q`, Linux, Python 3.13), inclusiv variantele de apel COM (fără / cu loc pentru [out]), oprirea, salvarea pe parcurs și logul fără titluri.
- Livrare: `git pull`, apoi din nou `Install.bat`. După primul scan, logul apare în `G:\My Drive\Dev\DocAudit\logs`.

## 0.1.3 — 2026-10-28
- Nou: pașii „Cum fac?” sus pe fiecare ecran (Sursă, Analiză, Grupuri, De aplicat, Arhivă și jurnal, Setări), în RO / EN / DE. Sunt deschiși până îi închizi; browserul ține minte. Cerut de Bogdan: „nu am instrucțiuni”.
- Nou: butonul „Verifică legătura cu OneNote” în Sursă (și în caseta de eroare). Verifică pe rând Windows, pywin32, OneNote desktop înregistrat, pornirea prin COM și notebook-urile deschise, cu ✓ / ✗ și ce e de făcut la primul ✗. Fără linie de comandă. Doar citire.
- CLI: `diagnose [--demo]`, aceleași verificări în linia de comandă.
- Nou: „Șterge” la fiecare extragere din „Sursă” → „Extrageri existente” (paginile extrase, grupurile și deciziile ei, doar de pe calculator; OneNote nu e atins) și „Resetează setările” în „Setări” (valorile de la instalare, scrierea oprită; extragerile rămân). Cerut de Bogdan.
- Reparat: „AttributeError: OneNote.Application.GetHierarchy” (raportat de Bogdan pe laptopul de lucru). Biblioteca de tipuri OneNote nu era găsită prin registru, așa că pywin32 ajungea la legarea dinamică, pe care OneNote nu o acceptă. Legătura (`extract/connect.py`) încearcă acum pe rând: biblioteca înregistrată, biblioteca citită direct din `ONENOTE.EXE`, `comtypes` (instalat acum de `Install.bat`), apoi legarea dinamică. Fiecare variantă e verificată cu o citire mică. „Verifică legătura cu OneNote” arată ce variantă a mers și ce a picat înainte. Aceeași legătură o folosesc și scrierea și notebook-ul de test.
- Reparat: după actualizare rula încă DocAudit-ul vechi (scurtătura doar deschidea browserul), de aceea apăreau texte ca „ui.source.treefail”. Acum o pornire de altă versiune îi cere celei vechi să se închidă și pornește în locul ei. Dacă cea veche e 0.1.2 sau mai veche și nu știe să se închidă, cea nouă pornește pe alt port.
- Teste: 123 trecute (`pytest -q`, Linux, Python 3.13).
- Livrare: `git pull`, apoi din nou `Install.bat` (instalează comtypes). O singură dată: închide DocAudit-ul vechi din iconița de lângă ceas.

## 0.1.2 — 2026-10-28
- Reparat: în „Sursă” nu se putea alege niciun notebook. Eroarea de la OneNote apărea doar 7 secunde într-un mesaj jos, iar dacă OneNote desktop nu dădea niciun notebook, lista rămânea goală, fără explicație. Acum eroarea (sau lista goală) rămâne în pagină, cu ce e de verificat. Raportat de Bogdan.
- Ierarhia și paginile se citesc și în schema XML OneNote 2010, nu doar 2013 (înainte ieșea o listă goală fără eroare).
- COM: dacă `OneNote.Application` nu pornește, se încearcă și `OneNote.Application.12`, apoi legarea dinamică; mesajul spune ce a eșuat la fiecare (inclusiv un cache `gen_py` stricat).
- Nou: câmpul „Link din browser (notebook de echipă)” în „Sursă”. Lipești adresa notebook-ului din OneNote pe web (SharePoint / OneDrive, `:o:/r/`, `onenote.aspx?id=`, `Doc.aspx?…wd=target(…)`, `onenote:https://…`) și DocAudit bifează notebook-ul (sau secțiunea) din OneNote desktop. Dacă notebook-ul nu e deschis în OneNote desktop, apare butonul „Deschide în OneNote desktop” (link `onenote:`), apoi se caută din nou. Link-ul e citit doar ca text: fără rețea, fără scriere în OneNote.
- CLI: `tree` arată și adresa fiecărui notebook; `tree --link URL` spune ce notebook / secțiune îi corespunde. `tree` și `extract` nu mai ies cu traceback când OneNote refuză cererea.
- Teste: 119 trecute (`pytest -q`, Linux, Python 3.13), inclusiv formele de link, schema 2010 și `/api/link`.
- Livrare: `git pull`, apoi din nou `Install.bat`.

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
