CREATE TABLE IF NOT EXISTS Ideas (
    message_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS Timezones (
    user_id INTEGER PRIMARY KEY,
    timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ReactionRoleMessages (
    message_id INTEGER PRIMARY KEY,
    origin_channel INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ReactionRolePairs (
    message_id INTEGER,
    emoji TEXT,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (message_id, emoji),
    FOREIGN KEY (message_id) REFERENCES ReactionRoleMessages(message_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Addresses (
    user_id INTEGER PRIMARY KEY,
    address TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS WeatherLocations (
    user_id INTEGER PRIMARY KEY,
    location TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Leaderboards (
    name TEXT PRIMARY KEY,
    definition TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS LeaderboardAliases (
    name TEXT PRIMARY KEY,
    definition TEXT NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (source) REFERENCES Leaderboards(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS LeaderboardData (
    user_id INTEGER,
    leaderboard TEXT,
    datum TEXT NOT NULL,
    main_unit TEXT NOT NULL,
    PRIMARY KEY (user_id, leaderboard),
    FOREIGN KEY (leaderboard) REFERENCES Leaderboards(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS HwdykGames (
    player_id INTEGER NOT NULL,
    guessed INTEGER NOT NULL,
    actual INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS Limes (
    filename TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ConnectionsPuzzles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    owner INTEGER NOT NULL,
    categories TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS PreferredModels (
    user_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL DEFAULT "openai"
);

CREATE TABLE IF NOT EXISTS CCReacts (
    message_id INTEGER PRIMARY KEY,
    cleared_by INTEGER,
    cleared_at TIMESTAMP
);
