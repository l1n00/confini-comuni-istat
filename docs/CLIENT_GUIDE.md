# Guida client non eseguibile

Questo documento descrive il comportamento atteso da un consumer. Non contiene
un'integrazione pronta da copiare e non modifica l'app esistente.

## Flusso a cache vuota

```text
1. Scarica 2026/index.json.
2. Salva indice, base URL, anno e manifest/build identity in cache.
3. Normalizza il nome ricevuto e ogni municipalities[].name:
   Unicode NFC; trim; spazi interni multipli ridotti a uno; case-fold Unicode.
4. confronta nomi normalizzati per uguaglianza completa.
5. Se un solo risultato, scarica 2026/comuni/{code}.geojson.
6. Se più risultati, filtra per regione/territorialUnit soltanto se l'app ha
   quel contesto; altrimenti mostra tutti i candidati e attendi la scelta.
7. Se nessun risultato, informa che il nome non è disponibile.
8. Prima di richiedere il GeoJSON, controlla che il codice sia una stringa di
   sei cifre e non uno dei codici in dataset.excludedMunicipalities.

Flusso alternativo per punti del progetto [longitudine, latitudine]:

1. Per ogni municipalities[].bbox, formato
   [minLon, minLat, maxLon, maxLat], considera candidato il comune quando
   minLon <= lon <= maxLon e minLat <= lat <= maxLat.
2. Scarica soltanto i GeoJSON dei candidati.
3. Applica ai loro confini il controllo preciso punto-in-poligono; il bbox è
   solo un filtro rapido e può includere falsi positivi.
4. Rimuovi i duplicati per codice e usa quei comuni per la selezione finale.
```

Il bbox comprende tutte le componenti di Polygon e MultiPolygon, comprese le
isole. I punti sul bordo del riquadro sono candidati; la geometria decide il
risultato definitivo. La ricerca per nome continua a usare il flusso originale.

Non usare somiglianza o punteggio fuzzy per scegliere automaticamente un nome.
Se l'app conosce il nome ma non regione/provincia, gli omonimi devono restare
visibili all'utente.

## Cache e correzioni

`/2026` non è immutabile. Una correzione ISTAT nello stesso anno può cambiare
`sourceManifestSha256` e `generatedAt`. Usa le normali intestazioni HTTP
`ETag` e/o `Last-Modified` per rivalidare l'indice; conserva anche la geometria
per codice e anno. Non trattare un file già scaricato come definitivo per sempre.

## GeoJSON ricevuto

Il file contiene una sola feature. La geometria può essere `Polygon` o
`MultiPolygon`; un comune con isole o parti disgiunte può quindi produrre più
geometrie elementari. Non trattare le parti come identità comunali separate:
l'identità è `feature.id`.

I cinque codici esclusi sono dichiarati in `dataset.excludedMunicipalities` e
non producono file: `072001`, `072037`, `072040`, `081019`, `087009`.
