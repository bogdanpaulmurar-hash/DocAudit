# DocAudit — instalare și testare pe Windows

DocAudit nu are încă interfață sau icon: deocamdată se folosește din linia de comandă, prin `DocAudit.bat`. Interfața web locală vine în Etapa 6, iar icon-ul din tray și integrarea în DevPilot în Etapa 8.

## 1. Instalare (o singură dată, fără admin)
1. Lasă Google Drive să termine sincronizarea, apoi în `G:\My Drive\Dev\DocAudit` rulează `git pull`.
2. Dublu clic pe **`Install.bat`**.
   - Creează mediul Python în `%LOCALAPPDATA%\DocAudit\venv` și instalează DocAudit. Repo-ul din Drive nu se modifică.
   - Ai nevoie de Python 3.11+ (din Microsoft Store sau de pe python.org).
3. La final apare versiunea, de exemplu „DocAudit 0.0.5”.

**Opțional, asemănarea după sens** (leagă aceeași procedură scrisă în română, engleză sau germană): `Install.bat semantic`. Descarcă modelul o singură dată (câteva sute de MB). Aceasta e singura comandă DocAudit care folosește internetul, iar după ea totul rulează offline.

**Actualizare:** după `git pull` nu trebuie reinstalat nimic, pentru că instalarea folosește direct fișierele din repo. Rulezi din nou `Install.bat` doar dacă CHANGELOG spune asta.

## 2. Unde stau datele
- Extragerile, grupurile și profilurile stau în `%LOCALAPPDATA%\DocAudit\data`, **local, nu în Google Drive**.
- În comenzi poți scrie doar numele unei extrageri (de exemplu `demo`) în loc de calea completă.

## 3. Test rapid, fără OneNote (5 minute)
Deschide un terminal (cmd) în folderul repo-ului și rulează:
1. `DocAudit.bat tree --demo` → afișează 3 notebook-uri fictive cu secțiunile lor.
2. `DocAudit.bat extract --demo` → „Gata: 80 pagini (80 citite …)”.
3. `DocAudit.bat extract --demo` din nou → „0 citite, 80 neschimbate” (extragere incrementală).
4. `DocAudit.bat group demo` → 15 grupuri, fiecare cu numărul de pagini și titlul.
5. `DocAudit.bat group demo --scan` → câte grupuri ies la fiecare prag.
6. `DocAudit.bat compare demo` → pentru fiecare grup: conflictele de valori (de exemplu portul 443 față de 8443), pașii lipsă sau în altă ordine, duplicatele, paginile probabil învechite și pagina care pare versiunea curentă. La final: „15 grupuri comparate: 20 conflicte, 6 diferențe de pași, 5 duplicate, 10 pagini probabil învechite. Nimic nu s-a modificat.”
7. `DocAudit.bat compare-eval demo` → „Conflicte găsite 20/20 …”.

## 4. Test pe OneNote, cu un notebook NOU de test
Pașii ating doar un notebook nou, creat cu eșantionul fictiv. Notebook-urile reale nu sunt atinse.
8. OneNote desktop (Microsoft 365 / 2016) trebuie să fie instalat. „OneNote for Windows 10” nu are COM.
9. `DocAudit.bat make-test-notebook "%USERPROFILE%\Documents\DocAudit Test"`
   - Așteptat: „Notebook de test creat: 82 pagini”. În OneNote apare „DocAudit Test” cu 3 grupuri de secțiuni și secțiunea „Arhivă” (2 pagini).
   - Folderul nu trebuie să existe; dacă există, comanda refuză.
10. `DocAudit.bat tree` → apar notebook-urile tale și „DocAudit Test”.
11. `DocAudit.bat extract --notebook "DocAudit Test" --out test`
   - Așteptat: 80 de pagini citite. Cele 2 din „Arhivă” nu intră.
12. `DocAudit.bat check-sample test` → „0 diferențe față de eșantion”. Dacă apar diferențe, trimite-mi lista: e fictivă și se poate copia.
13. Rulează din nou pasul 11 → „0 citite, 80 neschimbate”.
14. Modifică un cuvânt într-o pagină din „DocAudit Test”, apoi rulează pasul 11 → „1 citite, 79 neschimbate”.
15. `DocAudit.bat group test` → aceleași 15 grupuri ca la pasul 4.
16. `DocAudit.bat compare test` → aceleași constatări ca la pasul 6, cu excepția paginilor învechite: în notebook-ul de test toate paginile au data de azi, deci apar doar cele cu o versiune mai mică sau cu „nu mai folosiți” în text.

## 5. Opțional: un notebook real (doar citire)
17. `DocAudit.bat profile save real --notebook "<numele notebook-ului>"`, apoi `DocAudit.bat extract --profile real`.
18. `DocAudit.bat group real --scan`, apoi `DocAudit.bat group real`.
19. `DocAudit.bat compare real` → constatările pe grupurile reale. Rezultatul se salvează în `findings.json`, lângă date; OneNote nu se modifică.
    - Datele rămân local. Nu trimite conținutul: spune-mi doar câte pagini și grupuri au ieșit, ce prag pare bun, câte conflicte par reale și câte sunt alarme false, plus erorile, dacă apar.

## 6. Limbă și curățenie
- Mesajele apar în română. Pentru engleză sau germană: `set DOCAUDIT_LANG=en` sau `set DOCAUDIT_LANG=de` înainte de comenzi.
- Notebook-ul de test se închide din OneNote (clic dreapta → Închide acest notebook), iar folderul lui se poate șterge manual.
- Dezinstalare: șterge folderul `%LOCALAPPDATA%\DocAudit` (dispar și datele extrase).
