# KNOWN_ISSUES — DocAudit

Erori și modificări deschise. Când un punct e rezolvat și confirmat, se mută în CHANGELOG.md.

| ID | Tip | Descriere | Stare |
|---|---|---|---|
| 1 | risc | API-ul COM OneNote nu are „mută pagina” între secțiuni. Mutarea în Arhivă = copiere conținut (XML) în pagina nouă + pagina originală trimisă în Coșul OneNote (recuperabilă). De verificat pe un notebook de test că se păstrează imaginile, atașamentele, tag-urile și link-urile interne. | deschis |
| 2 | risc | COM merge doar cu OneNote desktop (Microsoft 365 / 2016), nu cu „OneNote for Windows 10”. Notebook-urile din SharePoint/OneDrive trebuie deschise și sincronizate local înainte de extragere. | deschis |
| 3 | risc | Politicile IT ale companiei pot bloca pywin32/COM sau instalarea de modele (embeddings, Tesseract). Fallback: import din export manual (.docx/.pdf/.mht pe secțiune) și grupare doar lexicală (fără model). | deschis |
| 6 | limită | Conflictele „de sens” (două fraze care se contrazic fără valori diferite) se detectează slab fără LLM local. LLM-ul local (Ollama) e opțional și oprit implicit. | deschis |
| 7 | limită | Datele de modificare OneNote se schimbă și la editări minore (ex. sincronizare, un tag adăugat), deci „cea mai nouă” nu înseamnă automat „corectă”. Raportul arată data ca indiciu, decizia rămâne la utilizator. | deschis |
| 8 | risc | Apelurile COM (`GetHierarchy`, `GetPageContent` cu parametri de ieșire prin pywin32) n-au rulat încă pe OneNote real. Codul încearcă două semnături; dacă ambele eșuează, `tree` afișează eroarea. De verificat cu `docs/TESTARE_WINDOWS.md`. | deschis |
| 9 | limită | OneNote nu permite setarea datei de modificare, deci în notebook-ul de test toate paginile par modificate azi. Notebook-ul verifică extragerea, nu detectarea paginilor învechite (aceea se testează pe eșantion). | deschis |
| 10 | limită | Exporturile .onepkg (pachet de notebook) nu sunt suportate; pentru import fără COM se folosesc .mht sau .docx per pagină. | deschis |
| 11 | limită | Eșantionul fictiv e mai ușor decât documentația reală (F1 1.00 la orice prag rezonabil), deci nu poate calibra pragul. Pragul implicit 0.6 trebuie verificat pe date reale cu `group --scan` și corecturi manuale. | deschis |
| 12 | risc | Asemănarea după sens (`--semantic`) n-a rulat cu un model real: modelul nu e instalat în mediul de test. Formula e testată cu scoruri simulate. | deschis |
