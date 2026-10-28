# MACTrack-web

Web interface for [MACTrack](https://github.com/spirit-of-light/MACTrack).

## Run

1. Start the MACTrack backend
2. `python3 -m http.server 8001 --bind 127.0.0.1`
3. Open <http://127.0.0.1:8001/>.

The backend only answers requests from its configured frontend origin
(default `http://127.0.0.1:8001`). For a backend elsewhere, open the page with
`?api=http://host:port`.
