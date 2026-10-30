"""Rappels rédigés à la main, à ne publier qu'après lecture des sources citées.

Chaque rappel disparaît seul à sa date `until`, pour ne pas présenter un fait ancien comme d'actualité.
"""
from datetime import date

RECALLS = {
    "sport": {
        "title": "Rappel : le Barça battu deux fois en cinq jours",
        "note": "Rappel rédigé par l'équipe Prisme. Scores vérifiés le 30 octobre 2026 sur les pages citées.",
        "until": "2026-11-15",
        "items": [
            {"date": "2026-10-25", "competition": "Liga, le Clásico", "match": "FC Barcelone 1-2 Real Madrid", "detail": "Au Camp Nou.",
             "sources": [{"name": "Sky Sports", "url": "https://www.skysports.com/football/news/13603624/barcelona-1-2-real-madrid-kylian-mbappe-scores-late-winner-in-el-clasico-to-beat-laliga-leaders"},
                         {"name": "Depor", "url": "https://depor.com/en/us-live/who-won-barcelona-vs-real-madrid-el-clasico-2026-final-score-result-and-goals-nnda-nnrt-noticia/?outputType=amp"}]},
            {"date": "2026-10-20", "competition": "Ligue des champions", "match": "Paris Saint-Germain 4-2 FC Barcelone", "detail": "",
             "sources": [{"name": "Hespress", "url": "https://fr.hespress.com/493306-ligue-des-champions-le-psg-prend-le-dessus-sur-le-fc-barcelone.html"},
                         {"name": "Cameroun24", "url": "https://cameroun24.net/article/76575-le-barca-tombe-face-au-psg-liverpool-arrache-un-succes-fou-tous-les-resultats-du-20-octobre.html"}]},
        ],
    },
}


def recall_for(slug, today=None):
    r = RECALLS.get(slug)
    return r if r and (today or date.today()).isoformat() <= r["until"] else None
