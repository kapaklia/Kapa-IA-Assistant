# Avvio con doppio clic

Apri **Kapa.desktop** nella cartella del progetto.
Se KDE chiede di autorizzare l'esecuzione del collegamento, conferma.
Puoi anche copiarlo sulla scrivania.

Per generare il collegamento dopo aver scaricato o spostato il progetto,
esegui una volta dalla sua cartella:

```bash
python3 scripts/installa_launcher.py --local
```

Il collegamento usa il Python di `.venv` o `venv`, se presenti, altrimenti
quello con cui esegui il comando. Le dipendenze della GUI devono essere
installate in quell'ambiente (`requirements-gui.txt`).

Per aggiungere invece Kapa al menu applicazioni, esegui
`python3 scripts/installa_launcher.py` con l'ambiente del progetto attivo.
Il collegamento locale contiene percorsi di questo PC ed è escluso da Git;
va rigenerato su ciascun computer.
