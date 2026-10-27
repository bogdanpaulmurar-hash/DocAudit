# Testare pe Windows — Etapa 3 (extragere din OneNote)

Pașii folosesc doar un notebook **nou**, creat cu eșantionul fictiv. Notebook-urile reale nu sunt atinse.

## Pregătire (o singură dată)
1. Închide alte sincronizări mari și lasă Google Drive să termine sincronizarea.
2. În `G:\My Drive\Dev\DocAudit`: `git pull`, apoi `pip install -e .[dev,windows]`.
3. OneNote desktop (Microsoft 365 / 2016) trebuie să fie instalat. „OneNote for Windows 10” nu are COM.
4. `pytest -q` → toate testele trec.

## Notebook de test
5. `python -m docaudit make-test-notebook "%USERPROFILE%\Documents\DocAudit Test"`
   - Așteptat: „Notebook de test creat: 82 pagini”. În OneNote apare notebook-ul „DocAudit Test” cu 3 grupuri de secțiuni și secțiunea „Arhivă” (2 pagini).
   - Folderul nu trebuie să existe; dacă există, comanda refuză.
6. `python -m docaudit tree` → apar notebook-urile tale și „DocAudit Test”, cu secțiunile și numărul de pagini.

## Extragere
7. `python -m docaudit extract --notebook "DocAudit Test" --out data\test`
   - Așteptat: 80 de pagini citite; cele 2 din „Arhivă” nu intră.
8. `python -m docaudit validate data\test` → „Format valid: 80 pagini”.
9. `python -m docaudit check-sample data\test` → „0 diferențe față de eșantion”. Dacă apar diferențe, trimite-mi lista (e fictivă, se poate copia).
10. Rulează din nou pasul 7 → „0 citite, 80 neschimbate”.
11. Modifică un cuvânt într-o pagină din „DocAudit Test”, apoi rulează pasul 7 → „1 citite, 79 neschimbate”.
12. `python -m docaudit profile save test --notebook "DocAudit Test"`, apoi `python -m docaudit extract --profile test` → același rezultat, în `data\test`.

## Opțional, pe un notebook real (doar citire)
13. `python -m docaudit extract --notebook "<numele tău>" --out data\real` și `python -m docaudit validate data\real`.
    - Datele rămân în `data\` (ignorat de git). Nu trimite conținutul; spune-mi doar numărul de pagini și erorile.

## Curățenie
- Notebook-ul de test se închide din OneNote (clic dreapta → Închide acest notebook), iar folderul se poate șterge manual.
