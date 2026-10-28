# DocAudit — instalare și testare pe Windows

DocAudit se folosește dintr-o interfață în browser, pornită din iconița de pe Desktop. Interfața rulează doar pe calculatorul tău (`127.0.0.1`), iar nimic nu pleacă în rețea. Comenzile din linia de comandă (`DocAudit.bat …`) rămân pentru test și automatizare.

## 1. Instalare (o singură dată, fără admin)
1. Lasă Google Drive să termine sincronizarea, apoi în `G:\My Drive\Dev\DocAudit` rulează `git pull`.
2. Dublu clic pe **`Install.bat`**.
   - Creează mediul Python în `%LOCALAPPDATA%\DocAudit\venv` și instalează DocAudit cu tot ce-i trebuie: iconița din tray (pystray, Pillow), unirea PDF-urilor pentru bot (pypdf) și asemănarea după sens. Repo-ul din Drive nu se modifică.
   - Creează scurtătura **DocAudit** pe Desktop și în meniul Start, cu iconiță.
   - Ai nevoie de Python 3.11+ (din Microsoft Store sau de pe python.org).
3. La final apare versiunea, de exemplu „DocAudit 0.1.0”.

**Asemănarea după sens** (leagă aceeași procedură scrisă în română, engleză sau germană) se instalează tot cu `Install.bat`, din 0.1.10. Modelul se descarcă o singură dată (câteva sute de MB); la rulările următoare doar se verifică. Aceasta e singura comandă DocAudit care folosește internetul, iar după ea totul rulează offline. Fără model și fără internet pentru el: `Install.bat baza`.

**Actualizare:** după fiecare `git pull` rulează din nou `Install.bat` (fără alt cuvânt după el). Pentru 0.1.0, da: adaugă iconița și scurtăturile.

## 2. Unde stau datele
- Extragerile, deciziile (`decisions.db`), setările și copiile de siguranță (`_backups`) stau în `%LOCALAPPDATA%\DocAudit\data`, **local, nu în Google Drive**.
- În comenzi poți scrie doar numele unei extrageri (de exemplu `demo`) în loc de calea completă.

## 3. Pornire
- Dublu clic pe **DocAudit** (Desktop sau meniul Start). Apare iconița în tray (lângă ceas) și se deschide browserul.
- Clic pe iconița din tray → „Deschide DocAudit”; „Închide” oprește serverul. Dacă DocAudit rulează deja, scurtătura doar deschide browserul. După o actualizare, scurtătura închide singură versiunea veche (de la 0.1.3 încolo); de la 0.1.2 sau mai vechi închide-o o dată din iconiță.
- Fără scurtătură: `DocAudit.bat ui` (oprești cu Ctrl+C).
- Limba (RO / EN / DE) se schimbă din colțul dreapta sus. Butonul 🌓 schimbă tema luminoasă / întunecată.

Fiecare ecran are sus „Cum fac?”, cu pașii lui.

Ecranele:
1. **Sursă**: bifezi notebook-urile, secțiunile sau paginile și apeși „Extrage”. „Arhivă” e exclusă implicit.
2. **Analiză**: pragul de asemănare, cu tabelul „câte grupuri la fiecare prag”, apoi „Rulează analiza”.
3. **Grupuri**: în stânga grupurile, ordonate după gravitate, cu filtre. În dreapta, constatările și paginile una lângă alta, cu valorile diferite evidențiate. Sub fiecare pagină ai deciziile: Referință, Învechită, Arhivează, Mută… (în altă secțiune: se deschide lista secțiunilor, cu căutare; dublu clic sau „Mută aici”), Lasă așa, Nu e în grup și Notă. Taste: `J`/`K` grupul următor / anterior, `1`–`9` alegi pagina, `R` / `O` / `A` / `I` decizi. Raportul se descarcă în HTML, CSV (Excel) sau Markdown.
4. **De aplicat**: previzualizarea exactă („pagina X se mută din Rețea în Arhivă”, „titlu nou: [ÎNVECHIT] …”) și butonul „Aplică”.
5. **Arhivă și jurnal**: ce s-a aplicat, cu „Restaurează”, și toate deciziile, cu „Anulează”.
6. **Setări**: prag, secțiunea de arhivă, prefixul, secțiunile excluse, portul și **„Permite scrierea în OneNote”** (oprită implicit).

## 4. Test rapid, fără OneNote (10 minute)
1. Pornește DocAudit. În **Sursă** bifează „Eșantion fictiv”, apoi „Extrage” → „Gata: 80 pagini”.
2. **Analiză** → „Rulează analiza” → 15 grupuri.
3. **Grupuri**: de exemplu „Instalare client VPN” arată portul 443 față de 8443 și versiunea 4.1 față de 5.2, plus pagina probabil învechită. Încearcă tastele și câteva decizii (Arhivează pe una, Învechită pe alta).
4. **De aplicat**: apar cele două decizii. Butonul „Aplică” e oprit (mod doar citire).
5. **Setări** → bifează „Permite scrierea în OneNote” → Salvează. Înapoi în **De aplicat** → „Aplică”. Pe eșantion se scrie doar într-un OneNote fals (`demo_onenote.json`), nu în OneNote-ul tău.
6. **Arhivă și jurnal** → „Restaurează” pe fiecare.
7. Din linia de comandă, același lucru: `DocAudit.bat extract --demo`, `DocAudit.bat group demo`, `DocAudit.bat compare demo` („20 conflicte, 6 diferențe de pași, 5 duplicate, 10 pagini probabil învechite”), `DocAudit.bat compare-eval demo`, `DocAudit.bat report demo`, `DocAudit.bat apply demo`.
8. La final, oprește din nou scrierea în **Setări**.

## 5. Test pe OneNote, cu un notebook NOU de test
Pașii ating doar un notebook nou, creat cu eșantionul fictiv. Notebook-urile reale nu sunt atinse.
1. OneNote desktop (Microsoft 365 / 2016) trebuie să fie instalat. „OneNote for Windows 10” nu are COM.
2. `DocAudit.bat make-test-notebook "%USERPROFILE%\Documents\DocAudit Test"`
   - Așteptat: „Notebook de test creat: 82 pagini”. În OneNote apare „DocAudit Test” cu 3 grupuri de secțiuni și secțiunea „Arhivă” (2 pagini).
   - Folderul nu trebuie să existe; dacă există, comanda refuză.
3. În **Sursă** (fără „Eșantion fictiv”) → „Arată notebook-urile” → bifează doar „DocAudit Test”, nume `test` → „Extrage” → 80 de pagini. Cele 2 din „Arhivă” nu intră.
   - Din linia de comandă: `DocAudit.bat extract --notebook "DocAudit Test" --out test`, apoi `DocAudit.bat check-sample test` → „0 diferențe față de eșantion”. Dacă apar diferențe, trimite-mi lista: e fictivă și se poate copia.
4. Extrage din nou → „0 citite, 80 neschimbate”. Modifică un cuvânt într-o pagină din „DocAudit Test” și extrage → „1 citite, 79 neschimbate”.
5. **Analiză** → aceleași 15 grupuri. **Grupuri** → aceleași conflicte. Dintre paginile învechite apar doar cele cu versiune mai mică sau cu „nu mai folosiți” în text, pentru că în notebook-ul de test toate paginile au data de azi.
6. **Scriere, doar în „DocAudit Test”**: alege „Arhivează” pe o pagină, „Mută…” pe alta (într-o altă secțiune a notebook-ului de test) și „Învechită” pe a treia. În **Setări** pornește scrierea, apoi **De aplicat** → „Aplică”.
   - În OneNote: prima pagină e acum în secțiunea „Arhivă” a notebook-ului „DocAudit Test”, cu nota „Mutat din: …” la început, iar originalul e în Coșul notebook-ului. Verifică imaginile, tabelele și listele.
   - A doua pagină are titlul „[ÎNVECHIT] …”.
   - În `%LOCALAPPDATA%\DocAudit\data\_backups` există câte o copie XML pentru fiecare pagină.
7. **Arhivă și jurnal** → „Restaurează” pe ambele → pagina revine în secțiunea ei, iar titlul își pierde prefixul.
8. Oprește scrierea din **Setări**. Spune-mi ce a mers și ce nu (mesajele de eroare, dacă apar).

## 6. Opțional: un notebook real (doar citire)
1. În **Sursă** bifează notebook-ul real, nume `real`, „Salvează selecția ca” `real` → „Extrage”.
2. **Analiză** → încearcă câteva praguri cu „Câte grupuri la fiecare prag”.
3. **Grupuri** → uită-te la conflicte. Nu porni scrierea pe notebook-ul real până nu a mers testul de la pasul 5.
   - Datele rămân local. Nu trimite conținutul: spune-mi doar câte pagini și grupuri au ieșit, ce prag pare bun, câte conflicte par reale și câte sunt alarme false.

## 7. Notebook de echipă (SharePoint / Teams) și „nu apare niciun notebook”
DocAudit citește doar din **OneNote desktop**. Un notebook deschis numai în browser nu apare în listă.
1. În **Sursă**, lipește în „Link din browser (notebook de echipă)” adresa notebook-ului din OneNote pe web (bara browserului) sau din OneNote desktop (clic dreapta pe notebook → Copiază linkul) → „Găsește notebook-ul”.
   - Dacă e deschis în OneNote desktop, DocAudit îl bifează (sau secțiunea din link). Apasă „Extrage”.
   - Dacă nu e, apasă „Deschide în OneNote desktop”, așteaptă sincronizarea, apoi din nou „Găsește notebook-ul”. Dacă butonul lipsește (link scurt de partajare), în OneNote pe web alege „Deschide în aplicația desktop”.
2. Dacă nu apare nimic sau apare o eroare, apasă **„Verifică legătura cu OneNote”** (în Sursă). Fiecare rând arată ✓ sau ✗, iar sub primul ✗ scrie ce ai de făcut. Rezolvă și apasă din nou. Trimite-mi textul rândurilor (se poate selecta și copia), nu conținutul paginilor.
   - Același lucru din linia de comandă: `DocAudit.bat diagnose`. Lista notebook-urilor cu adresa lor: `DocAudit.bat tree`; un link anume: `DocAudit.bat tree --link "<link>"`.
3. Fără COM (de exemplu blocat de IT): exportă paginile din OneNote ca .docx sau .mht și folosește `DocAudit.bat import-files <folder>`.

## 8. Notebook mare și logul tehnic
- Extragerea rulează în fundal, cu „Pagina N din M” și butonul **Oprește**. Ce s-a citit se salvează la fiecare 20 de pagini; „Extrage” din nou continuă de unde a rămas (paginile neschimbate nu se mai cer din OneNote).
- Dacă OneNote nu mai răspunde 3 minute la aceeași pagină (de exemplu a apărut fereastra „How do you want to start OneNote?”), DocAudit oprește singur extragerea și spune pagina. Alege Start Normally în OneNote, așteaptă sincronizarea și apasă din nou „Extrage”.
- Dacă primele pagini nu se pot citi deloc, extragerea se oprește singură după 5 încercări, cu eroarea afișată, în loc să încerce sute de pagini.
- **Logul tehnic** (Setări → Log tehnic) arată ce a făcut DocAudit: câte pagini, cât a durat, ce eroare a dat OneNote. Nu conține titluri, nume de notebook-uri sau text din pagini.
  - local: `%LOCALAPPDATA%\DocAudit\data\logs\docaudit.log`;
  - copie: `G:\My Drive\Dev\DocAudit\logs\pc-xxxxxx.log` (un fișier pe laptop), ca să o pot citi din Google Drive. Se oprește din Setări („Copie a logului în Google Drive”); folderul se poate schimba tot de acolo.
- După primul scan pe un notebook real, spune-mi doar „am rulat”: citesc logul din Drive.

### OneNote cade la fiecare pagină
- Semn: fereastra „How do you want to start OneNote?” apare iar și iar în timpul extragerii. Alege de fiecare dată **Start Normally**; nu șterge cache-ul sau setările (se pot pierde modificări nesincronizate).
- DocAudit încearcă singur mai multe căi de citire (PowerShell, pywin32, comtypes, legarea dinamică) și o ține minte pe cea care merge, deci căderea ar trebui să apară cel mult de câteva ori, doar la prima extragere.
- Dacă extragerea se oprește cu „OneNote cade la citirea paginilor pe toate căile”, trimite-mi logul (Setări → Log tehnic). Ca DocAudit să încerce din nou toate căile, șterge fișierul `%LOCALAPPDATA%\DocAudit\data\onenote_read.json`.

## 9. Export pentru bot (în locul scriptului vechi „1. Updating Script”)
- Ecranul **Export pentru bot**: paginile curățate devin PDF-uri pentru botul de documentație. Întâi „Analiză” și deciziile din „Grupuri”, ca paginile arhivate, învechite și duplicatele identice să rămână deoparte.
- Alege „Un document pe” (notebook / folder de sus / secțiune) și limita pe fișier (95 MB, botul primește maxim 100 MB). La „Folderul documentelor” poți pune folderul din care încarci în bot (cale completă, pe disc local sau OneDrive de firmă, **nu** în `G:\My Drive\Dev\DocAudit`).
- Verifică lista: o pagină debifată nu intră; din „Lăsate deoparte” poți bifa o pagină ca să intre totuși. „↺ automat” anulează alegerea ta.
- **Exportă**: fiecare pagină devine PDF prin OneNote (`Publish`, doar fișiere pe disc; OneNote nu se schimbă). Dacă PDF-ul nu merge, se încearcă prin Word, apoi prin pagina web, apoi din textul extras. Prima dată durează (pe 700 de pagini, probabil zeci de minute); după aceea se refolosesc PDF-urile paginilor neschimbate.
- La final: încarcă în bot **doar** fișierele din „De reîncărcat în bot”. Paginile din „De verificat de mână” (secțiuni cu parolă, pagini pe care OneNote nu le-a putut exporta) exportă-le tu din OneNote: Fișier → Export → Pagină → PDF.
- Folderul cu PDF-urile de la scriptul vechi: alege-l cu **Alege folderul…**. DocAudit îți arată fișierele care nu sunt ale lui și, dacă vrei, le mută în `_vechi_<dată>` (nu le șterge). După ce încarci documentele noi în bot, scoate-le pe cele vechi din bot.
- Pe lângă documente se face **`00_Cuprins.pdf`** (încarcă-l în bot; are lista documentelor și ultimele schimbări) și **instrucțiunile botului** (în ecran, butonul „Copiază”, și în `_Instructiuni_bot.md`). Instrucțiunile se pun în configurarea botului, nu printre documente; când ecranul spune că s-au schimbat, copiază-le din nou.
- Primul test: pune limita mică (de ex. 5 MB) și „Un document pe: secțiune” pe o extragere mică, ca să vezi cum se împart fișierele.

## 10. Limbă și curățenie
- Limba se schimbă din interfață. În linia de comandă: `set DOCAUDIT_LANG=en` sau `set DOCAUDIT_LANG=de` înainte de comenzi.
- Notebook-ul de test se închide din OneNote (clic dreapta → Închide acest notebook), iar folderul lui se poate șterge manual.
- Dezinstalare: șterge folderul `%LOCALAPPDATA%\DocAudit` (dispar și datele extrase) și scurtăturile DocAudit.
