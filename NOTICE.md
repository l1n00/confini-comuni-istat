# NOTICE — dati ISTAT e codice

## Dati pubblicati

**Attribuzione:** Istat, *Confini delle unità amministrative a fini statistici
al 1° gennaio 2026*, versione non generalizzata.

- Pagina fonte: <https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-al-1-gennaio-2018-2>
- Archivio upstream: <https://www.istat.it/storage/cartografia/confini_amministrativi/non_generalizzati/2026/Limiti01012026.zip>
- Descrizione tecnica: <https://www.istat.it/wp-content/uploads/2024/04/Descrizione-dati-Confini-unita-amministrative-fini-statistici.pdf>
- Open Data: <https://www.istat.it/dati/open-data/>
- Note legali: <https://www.istat.it/note-legali/>
- Licenza indicata dalle condizioni generali ISTAT: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.it)

Non è stato trovato un marker di licenza specifico per i file locali. Questo
progetto usa la base generale CC BY 4.0 documentata da ISTAT, senza affermare
di avere confermato una licenza file-specifica. Prima della pubblicazione va
ricontrollato il download e le sue eventuali condizioni particolari.

## Modifiche

- I dodici file shapefile locali consumati sono identificati per percorso
  relativo, dimensione e SHA-256 in `dist/source-manifest.json`.
- Le coordinate sono state trasformate da `EPSG:32632` a longitudine/latitudine
  WGS 84 secondo RFC 7946.
- Ogni record comunale valido è stato diviso in un GeoJSON indipendente.
- I cinque record non validi `072001`, `072037`, `072040`, `081019`, `087009`
  sono stati omessi senza riparazione, come richiesto esplicitamente dal
  proprietario del progetto. Sono elencati nei metadati dell'indice.
- Gli altri confini non sono stati semplificati, quantizzati deliberatamente o
  riparati.

I confini hanno finalità statistiche e non sostituiscono confini catastali o
legali.

## Codice

Nessuna licenza software è stata scelta. Un'eventuale licenza futura per il
codice deve essere separata dalla licenza e dai doveri di attribuzione dei dati
e non può rilicenziare il contenuto ISTAT.
