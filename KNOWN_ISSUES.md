# KNOWN_ISSUES — DocAudit

Erori și modificări deschise. Când un punct e rezolvat și confirmat, se mută în CHANGELOG.md.

| ID | Tip | Descriere | Stare |
|---|---|---|---|
| 1 | risc | API-ul COM OneNote nu are „mută pagina” între secțiuni. Mutarea în Arhivă = copiere conținut (XML) în pagina nouă + pagina originală trimisă în Coșul OneNote (recuperabilă). De verificat pe un notebook de test că se păstrează imaginile, atașamentele, tag-urile și link-urile interne. | deschis |
| 2 | risc | COM merge doar cu OneNote desktop (Microsoft 365 / 2016), nu cu „OneNote for Windows 10”. Notebook-urile din SharePoint/OneDrive trebuie deschise și sincronizate local înainte de extragere. | deschis |
| 3 | risc | Politicile IT ale companiei pot bloca pywin32/COM sau instalarea de modele (embeddings, Tesseract). Fallback: import din export manual (.docx/.pdf/.mht pe secțiune) și grupare doar lexicală (fără model). | deschis |
| 4 | întrebare | Repo-ul se numește `DocPilot`, proiectul `DocAudit`. De confirmat numele final (redenumire repo sau păstrare). | deschis |
| 5 | întrebare | Codul e generic (fără date de firmă), dar e folosit pe documentație de firmă. De confirmat că stă pe GitHub-ul personal și rulează pe laptopul de lucru (vezi WORK_RULES: separare). | deschis |
| 6 | limită | Conflictele „de sens” (două fraze care se contrazic fără valori diferite) se detectează slab fără LLM local. LLM-ul local (Ollama) e opțional și oprit implicit. | deschis |
| 7 | limită | Datele de modificare OneNote se schimbă și la editări minore (ex. sincronizare, un tag adăugat), deci „cea mai nouă” nu înseamnă automat „corectă”. Raportul arată data ca indiciu, decizia rămâne la utilizator. | deschis |
