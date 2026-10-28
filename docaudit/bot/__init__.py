"""„Export pentru bot”: paginile curățate devin documente PDF pentru un bot de documentație.

Pașii (preluați din vechiul script de export, refăcuți pe datele DocAudit):
1. `select` — ce pagini intră: fără duplicate exacte, pagini goale, pagini învechite sau
   arhivate; fiecare document = un notebook / un folder de sus / o secțiune.
2. `publish` — fiecare pagină devine PDF prin OneNote (Publish, doar fișiere pe disc), cu
   trepte de rezervă: PDF → Word → pagină web → text.
3. `pdf` + `export` — PDF-urile se unesc pe documente (sub limita botului, implicit 95 MB),
   cu un semn de carte pe pagină, și se face lista fișierelor care trebuie reîncărcate.
"""
