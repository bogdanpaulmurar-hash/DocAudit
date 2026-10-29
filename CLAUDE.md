# DocAudit — note pentru Claude
Reguli globale: GLOBAL_RULES.md (v1.2)

Verificator local de documentație exportată din OneNote: extrage paginile din notebook-urile alese, grupează paginile care descriu aceeași procedură, le compară și listează conflictele și paginile învechite pentru decizia utilizatorului. Python 3.12 pe Windows, interfață web locală (127.0.0.1) pornită din tray cu `pythonw -m docaudit`.

## Comenzi
- Instalare: `pip install -e .[dev]` (Python 3.11+); pe Windows `pip install -e .[dev,windows]` (pywin32 + comtypes pentru COM)
- Teste: `pytest -q` (CI: Ubuntu + Windows, Python 3.11 și 3.12)
- Eșantion fictiv: `python -m docaudit sample` (regenerează `tests/fixtures/sample_v1/`)
- Validare format: `python -m docaudit validate <folder>`
- Arbore OneNote: `python -m docaudit tree` (`--demo` = eșantionul, fără OneNote; `--link URL` = ce notebook corespunde link-ului din browser)
- Verificare OneNote: `python -m docaudit diagnose [--demo]` (Windows, pywin32, COM, notebook-uri; același lucru cu butonul din Sursă)
- Extragere: `python -m docaudit extract [--profile NUME | --notebook X --section "NB/S" --page ID] [--out DIR] [--full] [--demo]`
- Profiluri: `python -m docaudit profile save NUME --notebook X ...` · `python -m docaudit profile list` (în `data/profiles/`, sau `DOCAUDIT_DATA`)
- Import exporturi manuale: `python -m docaudit import-files FOLDER [--out DIR]` (.mht, .docx)
- Notebook de test (Windows, doar folder NOU): `python -m docaudit make-test-notebook FOLDER`; verificare: `python -m docaudit check-sample DIR`
- Grupare: `python -m docaudit group DIR [--threshold 0.6] [--semantic] [--scan]` → `DIR/groups.json`
- Corecturi: `python -m docaudit group-merge DIR A B` · `python -m docaudit group-detach DIR PAGINA` → `DIR/group_overrides.json`
- Evaluare pe eșantion: `python -m docaudit group-eval DIR` (precizie, acoperire, F1 pe perechi)
- Comparare: `python -m docaudit compare DIR` (după `group`) → `DIR/findings.json`; evaluare: `python -m docaudit compare-eval DIR`
- Asemănare după sens (opțional): `pip install -e .[semantic]` + modelul descărcat o dată; rulează offline
- Pe Windows: `Install.bat` (venv în `%LOCALAPPDATA%\DocAudit`, fără admin; din 0.1.10 instalează tot, inclusiv modelul semantic; `Install.bat baza` fără model). Bogdan rulează doar `Install.bat` după fiecare pull: nu-i cere alt argument, apoi `DocAudit.bat <comandă>`. Pașii de instalare și test: `docs/INSTALARE.md`
- Pornire obișnuită: `pythonw -m docaudit` (fără comandă: tray + browser) sau `python -m docaudit ui [--port N] [--no-browser]`
- Raport: `python -m docaudit report DIR [--format html|csv|md]`
- Aplicare în OneNote: `python -m docaudit apply DIR` (previzualizare) · `--yes` (scrie, doar cu scrierea pornită în setări) · `restore DIR NUMĂR`
- Export pentru bot: `python -m docaudit bot-export DIR [--out-dir DIR] [--full] [--plan]` (setările `bot_*` din `settings.json`)
- Iconiță: `python -m docaudit make-icon FOLDER` (o folosește `Install.bat` pentru scurtături)
- Log: în UI Setări → Log tehnic; fișierele `%LOCALAPPDATA%\DocAudit\data\logs\docaudit.log` și `<clona>\logs\pc-xxxxxx.log` (`DOCAUDIT_LOG_SHARE=0` oprește copia; testele o opresc)

## Hartă
- `docs/PLAN.md` — arhitectura, formatul de intrare, etapele, testul pe eșantion
- `KNOWN_ISSUES.md` — riscuri și întrebări deschise ale proiectului
- `CHANGELOG.md` — istoric, scris la commit
- `docaudit/model.py` — formatul normalizat v1 (Page, Manifest), citire/scriere, validare
- `docaudit/sample.py` — generatorul eșantionului fictiv (80 pagini) și `expected.json`
- `docaudit/safety.py` — `no_network()`, `tree_digest()`, `is_loopback()`
- `docaudit/i18n.py` + `docaudit/locales/{ro,en,de}.json` — texte vizibile
- `docaudit/lang.py` — limba paginii (ro/en/de) și expresiile de „pagină învechită” în cele trei limbi
- `Install.bat`, `DocAudit.bat` — instalare fără admin și rulare pe Windows (CRLF, fără diacritice)
- `docaudit/__main__.py` — CLI (`sample`, `validate`, `tree`, `extract`, `profile`, `import-files`, `make-test-notebook`, `check-sample`, `diagnose`, `group*`, `compare`, `compare-eval`, `ui`, `report`, `apply`, `restore`, `make-icon`, `download-model`)
- `docaudit/paths.py` — `data_dir()`, `resolve_folder()`, `backups_dir()`, `datasets()`
- `docaudit/settings.py` — setările în `data_dir()/settings.json`; `write_enabled` e `False` implicit (mod doar citire)
- `docaudit/extract/onenote_xml.py` — XML OneNote 2013 (ierarhie, pagină) → Page; `render_*` pentru teste și notebook-ul de test
- `docaudit/extract/connect.py` — legătura COM (mai multe variante) și `ComCaller`: încearcă parametrii cu / fără loc pentru [out] și ține minte varianta bună
- `docaudit/extract/com.py` — `ReadOnlyOneNote`: doar GetHierarchy și GetPageContent; căile de citire a paginilor (`WAYS`)
- `docaudit/extract/psbridge.py` — citirea paginilor printr-un proces PowerShell (doar GetPageContent, `-EncodedCommand`)
- `docaudit/log.py` — logul tehnic: local `data_dir()/logs/docaudit.log`, copie în `<clona>/logs/pc-xxxxxx.log` (Drive), ultimele rânduri în memorie pentru UI
- `docaudit/extract/run.py` — extragere cu selecție, incremental după data modificării, cache de imagini
- `docaudit/extract/selection.py` — bife (notebook / secțiune / pagină), excluderi („Arhivă”), profiluri
- `docaudit/extract/files.py` — import .mht / .docx (alternativa fără COM)
- `docaudit/extract/links.py` — link-ul din browser (SharePoint / OneDrive / `onenote:`) → notebook-ul din OneNote desktop, după atributul `path`; doar text, fără rețea
- `docaudit/extract/worker.py` — extragerea din UI într-un proces copil (`extract-worker`, comandă ascunsă), stare prin fișiere în `data_dir()/_jobs`
- `docaudit/extract/diagnose.py` — „Verifică legătura cu OneNote”: pașii pe rând, doar citire
- `docaudit/extract/demo.py` — OneNote fals care servește eșantionul (teste, lucru fără Windows)
- `docaudit/extract/check.py` — compară o extragere cu eșantionul
- `docaudit/testnotebook.py` — singurul cod care scrie în OneNote până la Etapa 7, doar într-un notebook NOU
- `docaudit/group/text.py` — normalizare (fără diacritice), titluri curățate, TF-IDF pe n-grame de caractere
- `docaudit/group/similarity.py` — scor pe perechi (text 0.7 + titlu 0.3; sensul poate doar ridica), candidați prin index inversat
- `docaudit/group/cluster.py` — grupuri de la perechea cea mai asemănătoare în jos, cu „unește” / „nu ține împreună”
- `docaudit/group/overrides.py`, `run.py`, `evaluate.py`, `semantic.py` — corecturi, rulare + `groups.json`, F1, embeddings locale
- `tests/fixtures/onenote/` — XML OneNote scris de mână (ierarhie cu Coș și grupuri, pagină cu liste, tabel, imagini, OCR)
- `tests/fixtures/sample_v1/` — eșantionul generat (verificat byte cu byte față de generator)
- `docaudit/compare/steps.py` — pașii paginii, valorile (cifre, căi, adrese, coduri) mascate cu `<v>`, alinierea pașilor între pagini
- `docaudit/compare/analyze.py` — pe grup: conflicte de valori, pași lipsă / în plus / în altă ordine, duplicate, pagini învechite (semne RO/EN/DE, versiune mai mică, valoare veche, dată), pagina sugerată ca referință
- `docaudit/compare/run.py`, `evaluate.py` — rulare + `findings.json`, scoruri pe eșantion
- `docaudit/decisions.py` — jurnalul deciziilor (SQLite `DIR/decisions.db`): cine, când, ce, de ce; anulare; ce s-a aplicat; editări (`rename`, `add_text`) pe lângă decizia paginii
- `docaudit/report.py` — `build_state()` (ce arată UI-ul) și raportul HTML / CSV / Markdown
- `docaudit/apply/` — `xmlops.py` (copie XML cu notă „Mutat din”, titlu cu prefix sau nou, text adăugat într-un bloc), `writer.py` (`ComOneNote` = scrierile prin pywin32; `FakeOneNote` pentru teste și demo), `pswriter.py` (aceleași scrieri prin PowerShell, folosite întâi), `run.py` (plan, apply, restore, copii de siguranță; arhivare, mutare, marcare)
- `docaudit/bot/` — „Export pentru bot”: `select.py` (ce pagini intră și de ce nu: duplicate identice, goale, învechite, arhivate; alegerile din `bot/overrides.json`), `publish.py` (`PowerShellPublisher`: doar OneNote `Publish` și Word → PDF; `OfflinePublisher`), `pdf.py` (PDF din text, unire `pypdf` sub limită cu semne de carte), `export.py` (trepte PDF → Word → MHT → text, cache pe pagină, lista de reîncărcat, fișierele străine mutate în `_vechi_…`), `guide.py` (`00_Cuprins.pdf` cu ultimele schimbări și `_Instructiuni_bot.md`, promptul botului: răspunde în RO / DE după limba întrebării); totul în `<extragere>/bot/`
- `docaudit/ui/server.py` + `ui/static/` — server din biblioteca standard doar pe 127.0.0.1 (Host verificat, jeton pe /api/, CSP), pagină unică fără build JS
- `docaudit/tray.py`, `docaudit/icon.py` — iconița din tray (pystray, opțional) și iconița desenată din cod (.png / .ico)
- `devpilot.tool.json` — descrierea pentru DevPilot

## Reguli ale proiectului
- **Nimic nu pleacă de pe calculator**: procesarea rulează local; fără apeluri de rețea în timpul analizei (test automat cu socket blocat). Serverul UI ascultă doar pe 127.0.0.1. Modelele (embeddings, OCR, LLM local) sunt opționale, descărcate o singură dată, rulate offline.
- **Logul tehnic** e singurul lucru care ajunge în Drive (copie în `logs/` din clonă, cerut de Bogdan ca să-l pot citi; se oprește din Setări). În log doar numere, durate, tipuri de eroare și locul din cod: niciodată titluri, nume de notebook-uri / secțiuni, id-uri sau text din pagini (test automat). Claude citește logul din Drive (`G:\My Drive\Dev\DocAudit\logs`) după un scan.
- **Nimic nu se șterge sau rescrie automat**: analiza e doar citire. Orice scriere în OneNote (arhivare, marcare) se face doar după decizia explicită a utilizatorului, cu previzualizare (dry-run) și copie de siguranță a paginii înainte.
- **Arhivare = mutare, nu ștergere**: pagina ajunge în secțiunea „Arhivă” (nume configurabil) cu o notă „Mutat din: <secțiune>, <dată>, <motiv>”; se poate restaura.
- **Date reale niciodată în repo**: `data/`, `exports/`, `*.db` sunt în `.gitignore`; testele folosesc doar eșantionul fictiv.
- Texte UI prin i18n (ro, en, de). Commit-uri în română.
- Documentația analizată e amestecată în română, engleză și germană: orice listă de cuvinte (titluri, semne de învechire) se scrie pentru toate trei, iar eșantionul conține pagini în toate trei.
- Datele extrase stau implicit în `%LOCALAPPDATA%\DocAudit\data` (`data_dir()`), niciodată în clona din Google Drive. Un nume simplu dat la `--out` sau ca folder ajunge tot acolo (`resolve_folder()`).
- Eșantionul nu are voie să dea indicii despre răspuns în id-uri sau în `source.ref`; dacă schimbi generatorul, regenerează fixture-ul (`python -m docaudit sample`) în același commit.
- Extragerea nu scrie în OneNote: `ReadOnlyOneNote` are doar cele două metode de citire (test automat). Singurul cod care scrie: `testnotebook.py` (doar notebook nou), `apply/writer.py` (`ComOneNote`) și `apply/pswriter.py` (`PowerShellWriter`), apelate doar din `apply/run.py`. `bot/publish.py` folosește doar `Publish` (fișier pe disc, OneNote neschimbat) și Word (test automat pe script).
- Documentele pentru bot: în `<extragere>/bot/out` sau în folderul ales (cale completă, niciodată în clona din Google Drive, verificat la salvarea setării). Din folderul ales se șterg doar fișierele scrise de un export DocAudit anterior.
- Scrierea în OneNote: doar decizii confirmate din previzualizare, doar cu `write_enabled` pornit, copie XML în `_backups` înainte, pagina modificată după extragere se sare, originalul ajunge în Coș (nu `deletePermanently`).
- Serverul UI: fără biblioteci externe, fără CORS, fără resurse de pe internet; tot textul paginilor intră în DOM prin `textContent`.
- Gruparea nu modifică paginile extrase; scrie doar `groups.json`. Compararea scrie doar `findings.json`; constatările sunt sugestii, nu se aplică singure. Corecturile utilizatorului (`group_overrides.json`) au prioritate față de scoruri și se păstrează între rulări.
- Imaginile se salvează ca `images/<sha256>.<ext>`; folosește `model.image_path()` ca să le găsești.
- Formatul de intrare are câmp `schema_version`; orice schimbare a lui = versiune nouă + migrare + notă în CHANGELOG.

## Stare
- v0.1.11 — botul nu are acces la OneNote: exportul face și cuprinsul cu ultimele schimbări și instrucțiunile botului; „Alege folderul…”, fișierele scriptului vechi mutate în `_vechi_…`.
- v0.1.9 — ecranul „Export pentru bot” (preluat din „1. Updating Script”): pagini curățate → PDF prin `Publish` cu trepte de rezervă → documente sub 95 MB → lista de reîncărcat. Netestat pe Windows real.
- v0.1.8 — decizia „Mută…” (secțiune aleasă din listă, aplicată ca arhivarea, restaurabilă); „Aplică” scrie prin PowerShell (`apply/pswriter.py`).
- v0.1.7 — paginile se citesc pe prima cale care nu face OneNote să cadă (PowerShell → pywin32 → comtypes → dinamic), ținută minte în `data_dir()/onenote_read.json`.
- v0.1.6 — extragerea din UI rulează în proces separat (`extract/worker.py`), oprit după 3 minute fără progres sau la „Oprește”; salvare la 20 de pagini.
- v0.1.5 — extragere robustă: OneNote căzut la GetPageContent (RPC 0x800706BA) → reconectare, reîncercare, pagina fără imagini; v0.1.4 a adus `ComCaller`, extragerea în fundal și logul tehnic (copie în Drive, scris rând cu rând).
- v0.1.3 — toate etapele din plan (1–8) sunt pe `main`: extragere, grupare, comparare, interfață cu jurnal și raport, aplicare în OneNote cu previzualizare / copie / restaurare, tray cu iconiță. Pe eșantion: grupare F1 1.00, conflicte 20/20, învechite 10/10. **Netestat pe Windows real**: COM (citire și scriere), `Install.bat` cu scurtături, tray (pașii în `docs/INSTALARE.md`). Riscurile deschise sunt în KNOWN_ISSUES.md și MODIFICARI_PROIECTE (Google Drive).
