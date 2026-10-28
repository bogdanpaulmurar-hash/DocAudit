# DocAudit — note pentru Claude
Reguli globale: GLOBAL_RULES.md (v1.2)

Verificator local de documentație exportată din OneNote: extrage paginile din notebook-urile alese, grupează paginile care descriu aceeași procedură, le compară și listează conflictele și paginile învechite pentru decizia utilizatorului. Python 3.12 pe Windows, interfață web locală (127.0.0.1) pornită din tray cu `pythonw -m docaudit`.

## Comenzi
- Instalare: `pip install -e .[dev]` (Python 3.11+); pe Windows `pip install -e .[dev,windows]` (pywin32 pentru COM)
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
- Pe Windows: `Install.bat` (venv în `%LOCALAPPDATA%\DocAudit`, fără admin; `Install.bat semantic` cu modelul), apoi `DocAudit.bat <comandă>`. Pașii de instalare și test: `docs/INSTALARE.md`
- Pornire obișnuită: `pythonw -m docaudit` (fără comandă: tray + browser) sau `python -m docaudit ui [--port N] [--no-browser]`
- Raport: `python -m docaudit report DIR [--format html|csv|md]`
- Aplicare în OneNote: `python -m docaudit apply DIR` (previzualizare) · `--yes` (scrie, doar cu scrierea pornită în setări) · `restore DIR NUMĂR`
- Iconiță: `python -m docaudit make-icon FOLDER` (o folosește `Install.bat` pentru scurtături)

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
- `docaudit/extract/com.py` — `ReadOnlyOneNote`: doar GetHierarchy și GetPageContent
- `docaudit/extract/run.py` — extragere cu selecție, incremental după data modificării, cache de imagini
- `docaudit/extract/selection.py` — bife (notebook / secțiune / pagină), excluderi („Arhivă”), profiluri
- `docaudit/extract/files.py` — import .mht / .docx (alternativa fără COM)
- `docaudit/extract/links.py` — link-ul din browser (SharePoint / OneDrive / `onenote:`) → notebook-ul din OneNote desktop, după atributul `path`; doar text, fără rețea
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
- `docaudit/decisions.py` — jurnalul deciziilor (SQLite `DIR/decisions.db`): cine, când, ce, de ce; anulare; ce s-a aplicat
- `docaudit/report.py` — `build_state()` (ce arată UI-ul) și raportul HTML / CSV / Markdown
- `docaudit/apply/` — `xmlops.py` (copie XML cu notă „Mutat din”, titlu cu prefix), `writer.py` (`ComOneNote` = singurele scrieri COM; `FakeOneNote` pentru teste și demo), `run.py` (plan, apply, restore, copii de siguranță)
- `docaudit/ui/server.py` + `ui/static/` — server din biblioteca standard doar pe 127.0.0.1 (Host verificat, jeton pe /api/, CSP), pagină unică fără build JS
- `docaudit/tray.py`, `docaudit/icon.py` — iconița din tray (pystray, opțional) și iconița desenată din cod (.png / .ico)
- `devpilot.tool.json` — descrierea pentru DevPilot

## Reguli ale proiectului
- **Nimic nu pleacă de pe calculator**: procesarea rulează local; fără apeluri de rețea în timpul analizei (test automat cu socket blocat). Serverul UI ascultă doar pe 127.0.0.1. Modelele (embeddings, OCR, LLM local) sunt opționale, descărcate o singură dată, rulate offline.
- **Nimic nu se șterge sau rescrie automat**: analiza e doar citire. Orice scriere în OneNote (arhivare, marcare) se face doar după decizia explicită a utilizatorului, cu previzualizare (dry-run) și copie de siguranță a paginii înainte.
- **Arhivare = mutare, nu ștergere**: pagina ajunge în secțiunea „Arhivă” (nume configurabil) cu o notă „Mutat din: <secțiune>, <dată>, <motiv>”; se poate restaura.
- **Date reale niciodată în repo**: `data/`, `exports/`, `*.db` sunt în `.gitignore`; testele folosesc doar eșantionul fictiv.
- Texte UI prin i18n (ro, en, de). Commit-uri în română.
- Documentația analizată e amestecată în română, engleză și germană: orice listă de cuvinte (titluri, semne de învechire) se scrie pentru toate trei, iar eșantionul conține pagini în toate trei.
- Datele extrase stau implicit în `%LOCALAPPDATA%\DocAudit\data` (`data_dir()`), niciodată în clona din Google Drive. Un nume simplu dat la `--out` sau ca folder ajunge tot acolo (`resolve_folder()`).
- Eșantionul nu are voie să dea indicii despre răspuns în id-uri sau în `source.ref`; dacă schimbi generatorul, regenerează fixture-ul (`python -m docaudit sample`) în același commit.
- Extragerea nu scrie în OneNote: `ReadOnlyOneNote` are doar cele două metode de citire (test automat). Singurul cod care scrie: `testnotebook.py` (doar notebook nou) și `apply/writer.py` (`ComOneNote`), apelat doar din `apply/run.py`.
- Scrierea în OneNote: doar decizii confirmate din previzualizare, doar cu `write_enabled` pornit, copie XML în `_backups` înainte, pagina modificată după extragere se sare, originalul ajunge în Coș (nu `deletePermanently`).
- Serverul UI: fără biblioteci externe, fără CORS, fără resurse de pe internet; tot textul paginilor intră în DOM prin `textContent`.
- Gruparea nu modifică paginile extrase; scrie doar `groups.json`. Compararea scrie doar `findings.json`; constatările sunt sugestii, nu se aplică singure. Corecturile utilizatorului (`group_overrides.json`) au prioritate față de scoruri și se păstrează între rulări.
- Imaginile se salvează ca `images/<sha256>.<ext>`; folosește `model.image_path()` ca să le găsești.
- Formatul de intrare are câmp `schema_version`; orice schimbare a lui = versiune nouă + migrare + notă în CHANGELOG.

## Stare
- v0.1.3 — toate etapele din plan (1–8) sunt pe `main`: extragere, grupare, comparare, interfață cu jurnal și raport, aplicare în OneNote cu previzualizare / copie / restaurare, tray cu iconiță. Pe eșantion: grupare F1 1.00, conflicte 20/20, învechite 10/10. **Netestat pe Windows real**: COM (citire și scriere), `Install.bat` cu scurtături, tray (pașii în `docs/INSTALARE.md`). Riscurile deschise sunt în KNOWN_ISSUES.md și MODIFICARI_PROIECTE (Google Drive).
