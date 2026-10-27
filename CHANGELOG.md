# CHANGELOG — DocAudit

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
