import sqlite3
import datetime
from collections import defaultdict
from openskill.models import PlackettLuce

model = PlackettLuce()
db = sqlite3.connect("config/the.db")

db.execute("""
CREATE TABLE NewHwdykGames (
    played_at TIMESTAMP,
    player_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    message_id INTEGER,
    guess INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    player_mu DOUBLE NOT NULL,
    player_sigma DOUBLE NOT NULL,
    author_mu DOUBLE NOT NULL,
    author_sigma DOUBLE NOT NULL
);
""")

player_ratings = defaultdict(model.rating)
author_ratings = defaultdict(model.rating)
for player_id, guessed, actual in db.execute("SELECT * FROM HwdykGames ORDER BY rowid"):
    [player_ratings[player_id]], [author_ratings[actual]] = model.rate([[player_ratings[player_id]], [author_ratings[actual]]], ranks=[1, 2] if actual == guessed else [2, 1])
    db.execute("INSERT INTO NewHwdykGames VALUES (NULL, ?, 1133026989637382144, NULL, ?, ?, ?, ?, ?, ?)", (player_id, guessed, actual, player_ratings[player_id].mu, player_ratings[player_id].sigma, author_ratings[actual].mu, author_ratings[actual].sigma))

for game, in db.execute("SELECT MAX(rowid) FROM NewHwdykGames GROUP BY player_id UNION SELECT MAX(rowid) FROM NewHwdykGames GROUP BY author_id"):
    db.execute("UPDATE NewHwdykGames SET played_at = ? WHERE rowid = ?", (datetime.datetime.now(datetime.timezone.utc).isoformat(), game))

db.execute("DROP TABLE HwdykGames")
db.execute("ALTER TABLE NewHwdykGames RENAME TO HwdykGames")
db.commit()
