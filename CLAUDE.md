# DocAudit — note pentru Claude
Reguli globale: GLOBAL_RULES.md (v1.2)

Verificator local de documentație exportată din OneNote: extrage paginile din notebook-urile alese, grupează paginile care descriu aceeași procedură, le compară și listează conflictele și paginile învechite pentru decizia utilizatorului. Python 3.12 pe Windows, interfață web locală (127.0.0.1) pornită din tray cu `pythonw`.

## Comenzi
- Instalare: `pip install -e .[dev]` (Python 3.11+, fără dependențe în nucleu deocamdată)
- Teste: `pytest -q` (CI: Ubuntu + Windows, Python 3.11 și 3.12)
- Eșantion fictiv: `python -m docaudit sample` (regenerează `tests/fixtures/sample_v1/`)
- Validare format: `python -m docaudit validate <folder>`
- Planificat (Etapa 8): `pythonw -m docaudit` (tray + UI)

## Hartă
- `docs/PLAN.md` — arhitectura, formatul de intrare, etapele, testul pe eșantion
- `KNOWN_ISSUES.md` — riscuri și întrebări deschise ale proiectului
- `CHANGELOG.md` — istoric, scris la commit
- `docaudit/model.py` — formatul normalizat v1 (Page, Manifest), citire/scriere, validare
- `docaudit/sample.py` — generatorul eșantionului fictiv (80 pagini) și `expected.json`
- `docaudit/safety.py` — `no_network()`, `tree_digest()`, `is_loopback()`
- `docaudit/i18n.py` + `docaudit/locales/{ro,en}.json` — texte vizibile
- `docaudit/__main__.py` — CLI (`sample`, `validate`)
- `tests/fixtures/sample_v1/` — eșantionul generat (verificat byte cu byte față de generator)
- Planificat: `docaudit/{extract,group,compare,report,decisions,apply,ui}/`

## Reguli ale proiectului
- **Nimic nu pleacă de pe calculator**: procesarea rulează local; fără apeluri de rețea în timpul analizei (test automat cu socket blocat). Serverul UI ascultă doar pe 127.0.0.1. Modelele (embeddings, OCR, LLM local) sunt opționale, descărcate o singură dată, rulate offline.
- **Nimic nu se șterge sau rescrie automat**: analiza e doar citire. Orice scriere în OneNote (arhivare, marcare) se face doar după decizia explicită a utilizatorului, cu previzualizare (dry-run) și copie de siguranță a paginii înainte.
- **Arhivare = mutare, nu ștergere**: pagina ajunge în secțiunea „Arhivă” (nume configurabil) cu o notă „Mutat din: <secțiune>, <dată>, <motiv>”; se poate restaura.
- **Date reale niciodată în repo**: `data/`, `exports/`, `*.db` sunt în `.gitignore`; testele folosesc doar eșantionul fictiv.
- Texte UI prin i18n (ro, en). Commit-uri în română.
- Eșantionul nu are voie să dea indicii despre răspuns în id-uri sau în `source.ref`; dacă schimbi generatorul, regenerează fixture-ul (`python -m docaudit sample`) în același commit.
- Formatul de intrare are câmp `schema_version`; orice schimbare a lui = versiune nouă + migrare + notă în CHANGELOG.

## Stare
- v0.0.2 — Etapa 1 (plan) aprobată, Etapa 2 (schelet, format v1, eșantion, teste) făcută. Testele rulează în CI și pe Windows; nimic legat de OneNote încă. Riscurile deschise sunt în KNOWN_ISSUES.md și MODIFICARI_PROIECTE (Google Drive).
