# KNOWN_ISSUES — DocAudit

Erori și modificări deschise. Când un punct e rezolvat și confirmat, se mută în CHANGELOG.md.

| ID | Tip | Descriere | Stare |
|---|---|---|---|
| 1 | risc | API-ul COM OneNote nu are „mută pagina” între secțiuni. Mutarea în Arhivă = copiere conținut (XML) în pagina nouă + pagina originală trimisă în Coșul OneNote (recuperabilă). De verificat pe un notebook de test că se păstrează imaginile, atașamentele, tag-urile și link-urile interne. | deschis |
| 2 | risc | COM merge doar cu OneNote desktop (Microsoft 365 / 2016), nu cu „OneNote for Windows 10”. Notebook-urile din SharePoint/OneDrive trebuie deschise și sincronizate local înainte de extragere. | deschis |
| 3 | risc | Politicile IT ale companiei pot bloca pywin32/COM sau instalarea de modele (embeddings, Tesseract). Fallback: import din export manual (.docx/.pdf/.mht pe secțiune) și grupare doar lexicală (fără model). | deschis |
| 6 | limită | Conflictele „de sens” (două fraze care se contrazic fără valori diferite) se detectează slab fără LLM local. LLM-ul local (Ollama) e opțional și oprit implicit. | deschis |
| 7 | limită | Datele de modificare OneNote se schimbă și la editări minore (ex. sincronizare, un tag adăugat), deci „cea mai nouă” nu înseamnă automat „corectă”. Raportul arată data ca indiciu, decizia rămâne la utilizator. | deschis |
| 8 | risc | Apelurile COM cu parametru de ieșire (`GetHierarchy`, `GetPageContent`, `OpenHierarchy`, `CreateNewPage`) diferă după legare (dinamică / biblioteca de tipuri / comtypes). Ierarhia merge pe laptopul de lucru; citirea paginilor pica (0 pagini) și e reparată în 0.1.4 fără test pe OneNote real. De confirmat din log după primul scan. | deschis |
| 9 | limită | OneNote nu permite setarea datei de modificare, deci în notebook-ul de test toate paginile par modificate azi. Notebook-ul verifică extragerea, nu detectarea paginilor învechite (aceea se testează pe eșantion). | deschis |
| 10 | limită | Exporturile .onepkg (pachet de notebook) nu sunt suportate; pentru import fără COM se folosesc .mht sau .docx per pagină. | deschis |
| 11 | limită | Eșantionul fictiv e mai ușor decât documentația reală (F1 1.00 la orice prag rezonabil), deci nu poate calibra pragul. Pragul implicit 0.6 trebuie verificat pe date reale cu `group --scan` și corecturi manuale. | deschis |
| 12 | risc | Asemănarea după sens (`--semantic`) n-a rulat cu un model real: modelul nu e instalat în mediul de test. Formula e testată cu scoruri simulate. | deschis |
| 13 | limită | Aceeași procedură scrisă în limbi diferite (RO / EN / DE) nu se grupează doar după text: e nevoie de asemănarea după sens (`Install.bat semantic`). Fără model, traducerile apar ca pagini separate. | deschis |
| 14 | risc | `Install.bat` n-a rulat încă pe Windows; instalarea editabilă dintr-un folder Google Drive poate fi lentă la prima rulare. | deschis |
| 15 | limită | Compararea pe eșantion iese perfectă (20/20 conflicte, 0 alarme false), dar eșantionul are pași în liste numerotate și valori clare. Pe date reale pot apărea pagini fără liste (pașii nu se găsesc), valori scrise în proză și alarme false din reformulări. De verificat cu `compare real`. | deschis |
| 16 | limită | Când un grup are doar două pagini cu pași în altă ordine, nu se poate spune care e cea corectă: constatarea le numește pe amândouă. | deschis |
| 17 | limită | Paginile în altă limbă decât restul grupului (traduceri) nu se compară pas cu pas, deci un conflict de valori între o pagină RO și una DE nu se vede încă. | deschis |
| 18 | risc | Scrierile COM (`OpenHierarchy` pentru secțiunea Arhivă, `CreateNewPage`, `UpdatePageContent` cu XML-ul copiat, `DeleteHierarchy` în Coș) n-au rulat pe OneNote real; sunt testate doar pe OneNote-ul fals. Paginile cu fișiere atașate, cerneală sau audio pot să nu se copieze complet. De verificat cu `docs/INSTALARE.md` pasul 5.6, doar pe notebook-ul de test. | deschis |
| 19 | limită | După arhivare sau restaurare, pagina are alt ID în OneNote; extragerea veche o vede ca pagină dispărută. Rulează din nou extragerea după „Aplică”. | deschis |
| 20 | risc | Tray-ul (pystray), scurtăturile create de `Install.bat` și pornirea cu `pythonw` n-au rulat pe Windows. Fără pystray, interfața pornește oricum, fără iconiță în tray. | deschis |
| 21 | de confirmat | Formatul `devpilot.tool.json` e propus de mine; trebuie potrivit cu ce citește DevPilot. | deschis |
| 22 | de confirmat | Notebook-ul de lucru are 700+ pagini. Extragerea cere fiecare pagină cu imaginile (base64); durata pe OneNote real nu e măsurată. Logul arată durata totală și paginile peste 20 s. Dacă e prea lent, se poate cere conținutul fără imagini la prima trecere. | deschis |
| 23 | de decis | Funcțiile din „1. Updating Script” (export PDF cu trepte de rezervă, duplicate exacte după hash, pagini „Untitled” excluse, documente comasate pentru bot sub 100 MB, lista fișierelor de reîncărcat) nu sunt încă în DocAudit. Exportul PDF are nevoie de `Publish` (COM), care nu e în `ReadOnlyOneNote`. | deschis |
| 24 | de confirmat | Pe laptopul de lucru (Python 3.14, legătura „OneNote.Application.12”) OneNote cade la fiecare `GetPageContent` prin pywin32, deși `GetHierarchy` merge. Cauza nu e cunoscută (legătura .12 / biblioteca de tipuri sau OneNote însuși). 0.1.7 trece la PowerShell / comtypes / dinamic și ține minte calea; scriptul PowerShell (`extract/psbridge.py`) n-a rulat încă pe Windows real. | deschis |
