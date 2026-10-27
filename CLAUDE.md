# DocAudit — note pentru Claude
Reguli globale: GLOBAL_RULES.md (v1.2)

Verificator local de documentație exportată din OneNote: extrage paginile din notebook-urile alese, grupează paginile care descriu aceeași procedură, le compară și listează conflictele și paginile învechite pentru decizia utilizatorului. Python 3.12 pe Windows, interfață web locală (127.0.0.1) pornită din tray cu `pythonw`.

## Comenzi
- Instalare: `pip install -e .[dev]` (Python 3.11+); pe Windows `pip install -e .[dev,windows]` (pywin32 pentru COM)
- Teste: `pytest -q` (CI: Ubuntu + Windows, Python 3.11 și 3.12)
- Eșantion fictiv: `python -m docaudit sample` (regenerează `tests/fixtures/sample_v1/`)
- Validare format: `python -m docaudit validate <folder>`
- Arbore OneNote: `python -m docaudit tree` (`--demo` = eșantionul, fără OneNote)
- Extragere: `python -m docaudit extract [--profile NUME | --notebook X --section "NB/S" --page ID] [--out DIR] [--full] [--demo]`
- Profiluri: `python -m docaudit profile save NUME --notebook X ...` · `python -m docaudit profile list` (în `data/profiles/`, sau `DOCAUDIT_DATA`)
- Import exporturi manuale: `python -m docaudit import-files FOLDER [--out DIR]` (.mht, .docx)
- Notebook de test (Windows, doar folder NOU): `python -m docaudit make-test-notebook FOLDER`; verificare: `python -m docaudit check-sample DIR`
- Pași de test pe Windows: `docs/TESTARE_WINDOWS.md`
- Planificat (Etapa 8): `pythonw -m docaudit` (tray + UI)

## Hartă
- `docs/PLAN.md` — arhitectura, formatul de intrare, etapele, testul pe eșantion
- `KNOWN_ISSUES.md` — riscuri și întrebări deschise ale proiectului
- `CHANGELOG.md` — istoric, scris la commit
- `docaudit/model.py` — formatul normalizat v1 (Page, Manifest), citire/scriere, validare
- `docaudit/sample.py` — generatorul eșantionului fictiv (80 pagini) și `expected.json`
- `docaudit/safety.py` — `no_network()`, `tree_digest()`, `is_loopback()`
- `docaudit/i18n.py` + `docaudit/locales/{ro,en}.json` — texte vizibile
- `docaudit/__main__.py` — CLI (`sample`, `validate`, `tree`, `extract`, `profile`, `import-files`, `make-test-notebook`, `check-sample`)
- `docaudit/extract/onenote_xml.py` — XML OneNote 2013 (ierarhie, pagină) → Page; `render_*` pentru teste și notebook-ul de test
- `docaudit/extract/com.py` — `ReadOnlyOneNote`: doar GetHierarchy și GetPageContent
- `docaudit/extract/run.py` — extragere cu selecție, incremental după data modificării, cache de imagini
- `docaudit/extract/selection.py` — bife (notebook / secțiune / pagină), excluderi („Arhivă”), profiluri
- `docaudit/extract/files.py` — import .mht / .docx (alternativa fără COM)
- `docaudit/extract/demo.py` — OneNote fals care servește eșantionul (teste, lucru fără Windows)
- `docaudit/extract/check.py` — compară o extragere cu eșantionul
- `docaudit/testnotebook.py` — singurul cod care scrie în OneNote până la Etapa 7, doar într-un notebook NOU
- `tests/fixtures/onenote/` — XML OneNote scris de mână (ierarhie cu Coș și grupuri, pagină cu liste, tabel, imagini, OCR)
- `tests/fixtures/sample_v1/` — eșantionul generat (verificat byte cu byte față de generator)
- Planificat: `docaudit/{group,compare,report,decisions,apply,ui}/`

## Reguli ale proiectului
- **Nimic nu pleacă de pe calculator**: procesarea rulează local; fără apeluri de rețea în timpul analizei (test automat cu socket blocat). Serverul UI ascultă doar pe 127.0.0.1. Modelele (embeddings, OCR, LLM local) sunt opționale, descărcate o singură dată, rulate offline.
- **Nimic nu se șterge sau rescrie automat**: analiza e doar citire. Orice scriere în OneNote (arhivare, marcare) se face doar după decizia explicită a utilizatorului, cu previzualizare (dry-run) și copie de siguranță a paginii înainte.
- **Arhivare = mutare, nu ștergere**: pagina ajunge în secțiunea „Arhivă” (nume configurabil) cu o notă „Mutat din: <secțiune>, <dată>, <motiv>”; se poate restaura.
- **Date reale niciodată în repo**: `data/`, `exports/`, `*.db` sunt în `.gitignore`; testele folosesc doar eșantionul fictiv.
- Texte UI prin i18n (ro, en). Commit-uri în română.
- Eșantionul nu are voie să dea indicii despre răspuns în id-uri sau în `source.ref`; dacă schimbi generatorul, regenerează fixture-ul (`python -m docaudit sample`) în același commit.
- Extragerea nu scrie în OneNote: `ReadOnlyOneNote` are doar cele două metode de citire (test automat). Codul care scrie (notebook de test, apoi Etapa 7) stă în module separate.
- Imaginile se salvează ca `images/<sha256>.<ext>`; folosește `model.image_path()` ca să le găsești.
- Formatul de intrare are câmp `schema_version`; orice schimbare a lui = versiune nouă + migrare + notă în CHANGELOG.

## Stare
- v0.0.3 — Etapa 3 (extragere) făcută și testată cu XML OneNote scris de mână și cu eșantionul. **Netestat pe OneNote real**: apelurile COM și notebook-ul de test (pașii în `docs/TESTARE_WINDOWS.md`). Riscurile deschise sunt în KNOWN_ISSUES.md și MODIFICARI_PROIECTE (Google Drive).
