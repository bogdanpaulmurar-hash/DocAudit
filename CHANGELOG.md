# CHANGELOG — DocAudit

## 0.0.2 — 2026-10-27
- Etapa 2: schelet Python (`pyproject.toml`, pachetul `docaudit`, CLI `sample` / `validate`), formatul normalizat v1 cu validare, i18n RO/EN. De ce: toate etapele următoare citesc același format, indiferent de sursă.
- Eșantion fictiv de 80 de pagini în 3 notebook-uri, cu `expected.json`: 15 grupuri, 20 de conflicte de valori în 12 grupuri, 6 grupuri cu pași lipsă/inversați, 10 pagini învechite, 5 duplicate, 3 traduceri RO→EN, 10 pagini-capcană, 15 pagini unice, 3 imagini duplicate pe 6 pagini.
- Garanții testate: niciun apel de rețea (`no_network`), nicio scriere în folderul analizat (`tree_digest`), server doar pe loopback (`is_loopback`).
- Decizii: proiectul și repo-ul se numesc DocAudit (repo redenumit din DocPilot), pe GitHub-ul personal (KNOWN_ISSUES 4 și 5 închise).
- Teste: 30 trecute (`pytest -q`, Linux, Python 3.13). Windows: CI adăugat, rezultatul în PR.
- Livrare: doar cod nou, nimic de instalat pentru utilizator încă.

## 0.0.1 — 2026-10-27
- Etapa 1: planul de arhitectură (`docs/PLAN.md`), CLAUDE.md, KNOWN_ISSUES.md, CHANGELOG.md după șabloanele dev-framework. De ce: fixăm formatul de intrare, regulile „doar local” și „fără ștergeri automate” înainte de cod.
- Teste: nu există încă (fără cod). Testul pe eșantionul de 50–100 pagini e descris în plan, se implementează la Etapa 2.
- Livrare: doar documentație.
