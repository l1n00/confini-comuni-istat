# Pubblicazione GitHub Pages

## Stato

Il dataset è localmente validato, ma non è ancora su GitHub. Questo documento
non autorizza creazione repository, commit, push o deploy. Tali operazioni
richiedono una decisione separata dell'owner su account e nome repository.

## Gate preliminari

Prima di qualsiasi pubblicazione, registra nell'handoff:

- test locale completo e relativo conteggio;
- `sourceBeforeSha256 == sourceAfterSha256`;
- `artifactSha256` prodotto dal report completo;
- `municipalityFiles == 7891` e tutti i conteggi pubblicati;
- esclusione esplicita dei cinque codici autorizzati;
- riepilogo dimensioni, durata e file più grandi;
- verifica attuale delle condizioni ISTAT e delle license;
- verifica attuale dei limiti/termini GitHub Pages;
- stima del traffico atteso.

La dimensione misurata è circa 278,15 MB raw per `dist`, ben sotto la soglia
preferenziale di 900.000.000 byte. Questo non costituisce approvazione: va
verificato anche il timeout di deploy, il traffico e l'idoneità ai termini
correnti. I limiti storicamente documentati sono: 1 GB massimo di sito,
10 minuti di timeout e 100 GB/mese soft; le condizioni vanno ricontrollate live
immediatamente prima della pubblicazione.

## Repository consentito

- `dist/2026/**`
- `dist/source-manifest.json`
- codice, test, `README.md`, `NOTICE.md`, documentazione, workflow e report

Escludere `.venv`, `.tools`, `.execution`, cache, shapefili, ZIP, segreti e
percorsi locali. Non pubblicare `reports/build-failure.json` come release.

## Verifica pre-push

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m istat_confini.cli verify-release --project-root .
.venv/Scripts/python.exe -m istat_confini.cli refresh-report --project-root . --reports-root reports
```

Il workflow GitHub Actions esegue test e `validate-artifact` prima del upload.
Il report locale con `artifactSha256` deve essere riletto prima di commit e push.

## Workflow

`.github/workflows/pages.yml` è manuale (`workflow_dispatch`) e richiede il
token `I_APPROVED_PUBLICATION`. Non rigenera i dati e non accede alla cartella
Downloads locale. L'upload usa esattamente `dist/`.

Dopo il commit e il push, ma solo con approvazione separata:

```powershell
gh workflow run pages.yml --repo OWNER/REPOSITORY --ref REF --field confirm_publication=I_APPROVED_PUBLICATION
```

La configurazione GitHub Pages e l'URL `https://OWNER.github.io/REPOSITORY/`
devono essere concordati prima del comando. Non si deve presumere che un
repository esista già.

## Verifica HTTP post-deploy

Con URL approvati:

```powershell
.venv/Scripts/python.exe scripts/verify_published_api.py https://OWNER.github.io/REPOSITORY
```

Il verificatore richiede HTTPS, 200 per indice e codici rappresentativi, 404
per codici inesistenti, media type JSON/GeoJSON, CORS, cache validator e
assenza di percorsi locali. Un redirect non è accettato come 404. Se uno di
questi controlli fallisce, il deploy non è considerato conforme.

## Aggiornamenti ISTAT

Per una nuova versione dei confini, aggiornare la directory dell'anno, il
manifest, la validazione e la documentazione. Non cambiare silenziosamente il
contenuto di `/2026` senza cambiare manifest/build identity e senza nota di
rilascio. Non applicare semplificazioni per far entrare il dataset in un host.
