# Procedura di pubblicazione — solo dopo approvazione

## Prima di qualsiasi caricamento

1. Leggere il rapporto locale `RAPPORTO_PUBBLICAZIONE.md`.
2. GPLv3-only è approvata e LICENSE è incluso. Conservare testo e dichiarazioni.
3. La provenienza dei quattro asset è ora dichiarata dal titolare in THIRD_PARTY.md.
   Conservare le dichiarazioni e verificare licenze delle dipendenze nelle versioni risolte.
4. Controllare il vero repository originale: lo snapshot attuale non contiene
   metadati Git validi. Non considerare la cronologia controllata.

## Audit del repository originale (locale, senza push)

```bash
git status --short --untracked-files=all
git ls-files
git log --all --oneline
git rev-list --objects --all
```

Controllare indice e tutti i commit/riferimenti con uno scanner di segreti locale
aggiornato (es. Gitleaks, redigendo i valori), includendo file cancellati, branch e tag.
Non incollare output contenente segreti in chat o issue. Verificare anche file
ignorati già tracciati con `git ls-files -ci --exclude-standard`.
Se emergono chiavi: revocarle, bonificare la cronologia e ripetere la scansione.
Non riscrivere cronologia condivisa senza una decisione esplicita del proprietario.

## Preparare l'esportazione pulita

Il repository locale pulito è in `dist/repository-github/`.

L'elenco esatto è `docs/FILE_DISTRIBUITI.txt`, derivato dalla allowlist in
`kapa/package_private.py`. LICENSE è incluso nella allowlist. Il manifesto
MANIFEST.sha256 è generato nell'archivio, non va copiato dal vecchio snapshot.

```bash
python -B scripts/package_private.py
```

Il builder rifiuta di sovrascrivere uno ZIP esistente: conservare la bozza altrove
prima di rigenerare il finale. Estrarre il nuovo ZIP in una cartella nuova e usare
quella come origine pulita per GitHub, escludendo il MANIFEST dal versionamento.
Conservare il manifesto nel pacchetto di Release. Non usare `git add .` sulla
cartella personale di lavoro. Verificare inventario e `git diff --cached --stat`
prima di creare il primo commit, quando autorizzato.

## Dopo autorizzazione esplicita dell'autore

1. Nella copia pulita, inizializzare Git se necessario, verificare `.gitignore` e
   aggiungere solo i file approvati. Creare il commit iniziale solo se autorizzato.
2. Creare su GitHub un repository vuoto con nome e visibilità approvati, senza
   README/licenza generati dal sito; configurare il remote e push solo se autorizzati.
3. Abilitare segnalazione privata vulnerabilità e controlli di sicurezza disponibili.
4. Dopo una nuova prova dell'archivio finale, creare il tag `v0.1.0-alpha` e una
   Release marcata pre-release, solo se autorizzati. Usare le note preparate e
   allegare ZIP finale e checksum. Non allegare un archivio con diritti degli asset ancora non chiariti.
5. Controllare README e link, scaricare nuovamente gli allegati e verificare checksum.

Nessuno di questi passaggi remoti è stato eseguito durante la preparazione.
