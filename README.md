# Confini comunali ISTAT 2026 — API statica

Generatore e API statica per i confini comunali **non generalizzati** ISTAT,
riferiti al **1° gennaio 2026**. Il progetto produce un indice
nome/codice/territorio e un GeoJSON RFC 7946 per comune. Gli shapefile originali
non vengono inclusi nella repository.

**Stato della build: validato.** La pubblicazione GitHub è eseguita tramite il
workflow manuale descritto in `docs/PUBLICATION.md`; l'artefatto non viene
rigenerato durante il deploy.

## Dati prodotti

- `dist/2026/index.json`: 7.891 comuni disponibili, ordinati per codice.
- `dist/2026/comuni/{codice}.geojson`: 7.891 confini dettagliati.
- `dist/source-manifest.json`: hash SHA-256 dei 12 file sorgente consumati.
- `reports/validation.json`: esito della validazione completa e dimensioni reali.
- `reports/feasibility.md`: riepilogo leggibile di byte, tempi e hosting.

Cinque sorgenti con anelli auto-intersecanti sono omessi senza riparazione:
`072001`, `072037`, `072040`, `081019`, `087009`. I loro nomi, motivi e codici
sono dichiarati in `dataset.excludedMunicipalities`; non compaiono tra i comuni
cercabili e non hanno endpoint. Questa scelta è esplicita e non nasconde altri
errori: qualsiasi nuova geometria non valida blocca l'intera build.

## Uso da parte dell'app

A cache vuota sono sufficienti due richieste:

```text
GET https://l1n00.github.io/confini-comuni-istat/2026/index.json
GET https://l1n00.github.io/confini-comuni-istat/2026/comuni/{codice-6-cifre}.geojson
```

1. Scarica e conserva in cache l'indice.
2. Confronta il nome in modo completo; in caso di omonimia usa `region` e
   `territorialUnit` oppure mostra i candidati all'utente.
3. Scarica soltanto il GeoJSON del codice selezionato.

Ogni voce dell'indice contiene anche:

```json
"bbox": [minLon, minLat, maxLon, maxLat]
```

L'indice usa `schemaVersion: 2`. Ogni bbox è espresso con 6 decimali e
arrotondato verso l'esterno (ovest/sud per difetto, est/nord per eccesso),
quindi contiene sempre l'intera geometria con un errore massimo di circa 11 cm.
Per cercare i comuni che contengono i punti del progetto, usa il bbox come
filtro rapido, scarica i soli GeoJSON candidati e applica il controllo preciso
punto-in-poligono. Il bbox da solo può produrre falsi positivi.

I codici sono stringhe: `001235` non deve diventare `1235`. I cinque comuni
esclusi non hanno file. I percorsi `/2026` possono essere corretti dopo una
revisione ISTAT: usa `ETag`/`Last-Modified`, non una cache permanente basata
solo sull'URL. Vedi `docs/CLIENT_GUIDE.md`.

## Conversione e integrità

- Sorgente: shapefile comunale ISTAT 2026 non generalizzato.
- CRS verificato dai `.prj`: WGS 84 / UTM zone 32N (`EPSG:32632`).
- Output: WGS 84 longitudine/latitudine secondo RFC 7946.
- Nessuna semplificazione (nessuna decimazione dei vertici), quantizzazione
  deliberata, riparazione o rimozione per i comuni pubblicati.
- Poligoni con isole e buchi interni mantenuti come `MultiPolygon`/`Polygon`.
- Nomi e accenti UTF-8 senza BOM.
- Ogni file contiene una sola `Feature`; il nome del file, `id`,
  `properties.code` e `metadata.code` coincidono.

I confini sono statistici, non catastali o legali.

## Riprodurre la validazione

Richiede Python 3.12. Usare un ambiente virtuale:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest -q
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m istat_confini.cli build `
  --source-root 'C:\percorso\Limiti01012026' `
  --output-root dist `
  --reports-root reports
```

Il comando non sovrascrive un output esistente. Crea in una directory temporanea,
convalida l'artefatto contro la sorgente e solo allora lo promuove.
Per un controllo successivo non leggente dalla sorgente:

```powershell
.venv/Scripts/python.exe -m istat_confini.cli verify-release --project-root .
```

Per ripetere la sola inventario diagnostico della sorgente, scegli un nuovo nome:

```powershell
.venv/Scripts/python.exe -m istat_confini.diagnose `
  --source-root 'C:\percorso\Limiti01012026' `
  --report reports/new-source-audit.json
```

## Fonte, attribuzione e licenza

Fonte: [Istat, confini delle unità amministrative](https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-al-1-gennaio-2018-2),
versione non generalizzata al 1° gennaio 2026. La data di esportazione DBF
rilevata è 18 febbraio 2026 ed è distinta dalla data di riferimento.

Istat dichiara in [Open Data](https://www.istat.it/dati/open-data/) e nelle
[note legali](https://www.istat.it/note-legali/) la base
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
Non è stato trovato un indicatore di licenza specifico nei file locali: prima
della pubblicazione va ricontrollata l'assenza di condizioni difformi sul
download. L'artefatto conserva fonte, attribuzione, trasformazione CRS/formato
e l'assenza di semplificazione.

La licenza del codice non è ancora stata scelta e non può rilicenziare i dati.
Vedi `NOTICE.md` e `docs/PUBLICATION.md`.
