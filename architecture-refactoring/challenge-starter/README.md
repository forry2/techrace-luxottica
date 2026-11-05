# WareFlow

Sistema interno di gestione magazzino per NordShip. Gira in produzione da
anni - costruito nel tempo da diversi contractor, l'ultimo dei quali ha
lasciato l'azienda circa un anno fa.

## Avvio locale

```bash
pip install -r requirements-dev.txt
python main.py
```

L'app parte sulla porta 8080.

## Endpoint principali

```
GET  /warehouses                   -> elenco magazzini
GET  /stock/<sku>                  -> disponibilita' attuale di un articolo
POST /stock/<sku>/restock          -> aggiunge disponibilita' (uso interno/test)
POST /orders                       -> crea un ordine in stato DRAFT
GET  /orders                       -> elenco ordini
GET  /orders/<id>                  -> dettaglio ordine
POST /orders/<id>/confirm          -> conferma l'ordine, scala lo stock, genera la spedizione
POST /orders/<id>/cancel           -> annulla un ordine non confermato
GET  /shipments                    -> elenco spedizioni
```

## Test

```bash
pytest
```

## Note

- Le notifiche al cliente vengono inviate via email (nessun servizio SMTP
  reale collegato in questo ambiente - il contenuto viene solo loggato).
- Lo stock e' tenuto in cache in memoria per evitare di interrogare il
  database ad ogni richiesta.
