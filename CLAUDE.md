# DocAudit — note pentru Claude
Reguli globale: GLOBAL_RULES.md (v1.2)

Verificator local de documentație exportată din OneNote: extrage paginile din notebook-urile alese, grupează paginile care descriu aceeași procedură, le compară și listează conflictele și paginile învechite pentru decizia utilizatorului. Python 3.12 pe Windows, interfață web locală (127.0.0.1) pornită din tray cu `pythonw`.

## Comenzi
- Etapa 1: doar plan, încă fără cod. Comenzile se completează la Etapa 2.
- Planificat: `pip install -e .[dev]` · `pythonw -m docaudit` (tray + UI) · `pytest` · `python -m docaudit.sample` (eșantion fictiv)

## Hartă
- `docs/PLAN.md` — arhitectura, formatul de intrare, etapele, testul pe eșantion
- `KNOWN_ISSUES.md` — riscuri și întrebări deschise ale proiectului
- `CHANGELOG.md` — istoric, scris la commit
- Planificat: `docaudit/{extract,normalize,group,compare,report,decisions,apply,ui}/`, `tests/fixtures/sample_v1/`

## Reguli ale proiectului
- **Nimic nu pleacă de pe calculator**: procesarea rulează local; fără apeluri de rețea în timpul analizei (test automat cu socket blocat). Serverul UI ascultă doar pe 127.0.0.1. Modelele (embeddings, OCR, LLM local) sunt opționale, descărcate o singură dată, rulate offline.
- **Nimic nu se șterge sau rescrie automat**: analiza e doar citire. Orice scriere în OneNote (arhivare, marcare) se face doar după decizia explicită a utilizatorului, cu previzualizare (dry-run) și copie de siguranță a paginii înainte.
- **Arhivare = mutare, nu ștergere**: pagina ajunge în secțiunea „Arhivă” (nume configurabil) cu o notă „Mutat din: <secțiune>, <dată>, <motiv>”; se poate restaura.
- **Date reale niciodată în repo**: `data/`, `exports/`, `*.db` sunt în `.gitignore`; testele folosesc doar eșantionul fictiv.
- Texte UI prin i18n (ro, en). Commit-uri în română.
- Formatul de intrare are câmp `schema_version`; orice schimbare a lui = versiune nouă + migrare + notă în CHANGELOG.

## Stare
- v0.0.1 — Etapa 1 (plan) propusă, în așteptarea aprobării. Nimic testat pe Windows. Riscurile deschise sunt în KNOWN_ISSUES.md și MODIFICARI_PROIECTE (Google Drive).
