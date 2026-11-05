"""SQLite persistence. Parameterized queries; transaction-sized synchronous work."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SCHEMA = '''
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, joined TEXT NOT NULL, last_seen TEXT NOT NULL,
 blocked INTEGER NOT NULL DEFAULT 0, reachable INTEGER NOT NULL DEFAULT 1,
 notifications INTEGER NOT NULL DEFAULT 1, pending TEXT
);
CREATE TABLE IF NOT EXISTS activity (
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, day TEXT,
 PRIMARY KEY(user_id,day)
);
CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS movies (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('movie','series')), genre TEXT NOT NULL DEFAULT '',
 year INTEGER NOT NULL DEFAULT 0, country TEXT NOT NULL DEFAULT '',
 description TEXT NOT NULL DEFAULT '', duration INTEGER NOT NULL DEFAULT 0,
 poster TEXT NOT NULL DEFAULT '', trailer TEXT NOT NULL DEFAULT '',
 hidden INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
 language TEXT NOT NULL, quality TEXT NOT NULL, season INTEGER NOT NULL DEFAULT 0,
 episode INTEGER NOT NULL DEFAULT 0, file_id TEXT NOT NULL, media_type TEXT NOT NULL,
 UNIQUE(movie_id,language,quality,season,episode)
);
CREATE TABLE IF NOT EXISTS marks (
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE, kind TEXT NOT NULL,
 PRIMARY KEY(user_id,movie_id,kind)
);
CREATE TABLE IF NOT EXISTS ratings (
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
 score INTEGER CHECK(score BETWEEN 1 AND 5), PRIMARY KEY(user_id,movie_id)
);
CREATE TABLE IF NOT EXISTS deliveries (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
 movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE, sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS deliveries_movie ON deliveries(movie_id);
CREATE TABLE IF NOT EXISTS channels (
 id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER UNIQUE NOT NULL, title TEXT NOT NULL,
 url TEXT NOT NULL, required INTEGER NOT NULL DEFAULT 0, source INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS states (user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
 movie_id INTEGER REFERENCES movies(id) ON DELETE SET NULL, text TEXT, created TEXT
);
CREATE TABLE IF NOT EXISTS imports (
 chat_id INTEGER, message_id INTEGER, PRIMARY KEY(chat_id,message_id)
);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue (
 id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
 user_id INTEGER REFERENCES users(id), state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
 UNIQUE(job_id,user_id)
);
CREATE INDEX IF NOT EXISTS queue_pending ON queue(state,next_at);
'''

class Store:
    def __init__(self, path, timezone='Asia/Tashkent'):
        self.path = str(path)
        self.timezone = ZoneInfo(timezone)
        if self.path != ':memory:':
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def now(self):
        return datetime.now(self.timezone).isoformat(timespec='seconds')

    def all(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.conn.execute(sql, args).fetchone()
        return dict(r) if r else None

    def run(self, sql, args=()):
        with self.conn:
            c = self.conn.execute(sql, args)
        return c.lastrowid

    def touch(self, uid):
        now = self.now()
        with self.conn:
            self.conn.execute('INSERT INTO users(id,joined,last_seen) VALUES(?,?,?) '
                              'ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,reachable=1', (uid,now,now))
            self.conn.execute('INSERT OR IGNORE INTO activity VALUES(?,?)', (uid, now[:10]))
        return self.one('SELECT * FROM users WHERE id=?', (uid,))

    def role(self, uid, owners):
        if uid in owners:
            return 'owner'
        r = self.one('SELECT role FROM admins WHERE user_id=?', (uid,))
        return r['role'] if r else ''

    def state(self, uid):
        row = self.one('SELECT payload FROM states WHERE user_id=?', (uid,))
        return json.loads(row['payload']) if row else None

    def set_state(self, uid, state):
        if state is None:
            self.run('DELETE FROM states WHERE user_id=?', (uid,))
        else:
            self.run('INSERT INTO states VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload',
                     (uid, json.dumps(state, ensure_ascii=False)))

    def movie(self, mid, public=True):
        return self.one('SELECT * FROM movies WHERE id=?' + (' AND hidden=0' if public else ''), (mid,))

    def by_code(self, code, public=True):
        return self.one('SELECT * FROM movies WHERE code=?' + (' AND hidden=0' if public else ''), (code,))

    def create_movie(self, data):
        keys = ['code','title','kind','genre','year','country','description','duration','poster','trailer']
        vals = [data.get(k, 0 if k in ('year','duration') else '') for k in keys]
        return self.run(f'INSERT INTO movies({",".join(keys)},created) VALUES({",".join("?" for _ in range(11))})', vals+[self.now()])

    def create_with_asset(self, movie, asset):
        # A fresh code is mandatory; movie and first video commit together.
        if self.by_code(movie['code'],False):
            raise ValueError('Bu kod boshqa admin tomonidan band qilindi. /cancel qilib boshqa kod tanlang.')
        with self.conn:
            keys = ['code','title','kind','genre','year','country','description','duration','poster','trailer']
            mid = self.conn.execute(f'INSERT INTO movies({",".join(keys)},created) VALUES({",".join("?" for _ in range(11))})',
                    [movie[k] for k in keys]+[self.now()]).lastrowid
            season,episode=asset.get('season',0),asset.get('episode',0)
            if (movie['kind']=='series' and (season<1 or episode<1)) or (movie['kind']=='movie' and (season or episode)):
                raise ValueError('Fasl va qism kino turiga mos emas.')
            self.conn.execute('INSERT INTO assets(movie_id,language,quality,season,episode,file_id,media_type) VALUES(?,?,?,?,?,?,?)',
                              (mid,asset['language'],asset['quality'],season,episode,asset['file_id'],asset['media_type']))
        return mid

    def add_asset(self, mid, data):
        movie = self.movie(mid, public=False)
        if not movie:
            raise ValueError('Kino topilmadi.')
        season, episode = data.get('season',0), data.get('episode',0)
        if (movie['kind'] == 'series' and (season < 1 or episode < 1)) or (
            movie['kind'] == 'movie' and (season or episode)):
            raise ValueError('Fasl/qism kino turiga mos emas.')
        with self.conn:
            fresh = not self.one('SELECT id FROM assets WHERE movie_id=? AND season=? AND episode=?', (mid,season,episode))
            cur = self.conn.execute('INSERT INTO assets(movie_id,language,quality,season,episode,file_id,media_type) VALUES(?,?,?,?,?,?,?)',
                         (mid,data['language'],data['quality'],season,episode,data['file_id'],data['media_type']))
            if fresh and movie['kind']=='series' and not movie['hidden']:
                self._episode_job(mid,season,episode)
            return cur.lastrowid

    def import_post(self, chat, message, data):
        # One transaction ensures invalid/duplicate assets do not leave empty titles.
        with self.conn:
            if self.one('SELECT 1 FROM imports WHERE chat_id=? AND message_id=?', (chat,message)):
                return None
            movie = self.by_code(data['code'], public=False)
            if movie and (movie['title'] != data['title'] or movie['kind'] != data['kind']):
                raise ValueError('Bu kod boshqa nomdagi kinoga tegishli.')
            if movie:
                mid = movie['id']
            else:
                keys = ['code','title','kind','genre','year','country','description','duration','poster','trailer']
                mid = self.conn.execute(f'INSERT INTO movies({",".join(keys)},created) VALUES({",".join("?" for _ in range(11))})',
                                       [data[k] for k in keys]+[self.now()]).lastrowid
            fresh = not self.one('SELECT id FROM assets WHERE movie_id=? AND season=? AND episode=?', (mid,data['season'],data['episode']))
            self.conn.execute('INSERT INTO assets(movie_id,language,quality,season,episode,file_id,media_type) VALUES(?,?,?,?,?,?,?)',
                              (mid,data['language'],data['quality'],data['season'],data['episode'],data['file_id'],data['media_type']))
            self.conn.execute('INSERT INTO imports VALUES(?,?)', (chat,message))
            if fresh and data['kind']=='series' and not (movie and movie['hidden']):
                self._episode_job(mid,data['season'],data['episode'])
            return mid

    def _episode_job(self, mid, season, episode):
        payload = json.dumps({'movie_id':mid,'season':season,'episode':episode})
        jid = self.conn.execute('INSERT INTO jobs(kind,payload,created) VALUES(?,?,?)', ('episode',payload,self.now())).lastrowid
        self.conn.execute('INSERT INTO queue(job_id,user_id) SELECT ?,u.id FROM users u JOIN marks m ON m.user_id=u.id '
                          "WHERE m.movie_id=? AND m.kind='follow' AND u.notifications=1 AND u.blocked=0 AND u.reachable=1", (jid,mid))

    def broadcast(self, chat_id, message_id, creator):
        with self.conn:
            jid = self.conn.execute('INSERT INTO jobs(kind,payload,created) VALUES(?,?,?)',
                       ('broadcast',json.dumps({'chat_id':chat_id,'message_id':message_id,'creator':creator}),self.now())).lastrowid
            self.conn.execute('INSERT INTO queue(job_id,user_id) SELECT ?,id FROM users '
                              'WHERE notifications=1 AND blocked=0 AND reachable=1', (jid,))
        return jid

    def mark(self, uid, mid, kind):
        if kind not in ('favorite','later','follow'):
            raise ValueError('Noma’lum ro‘yxat.')
        with self.conn:
            exists = self.one('SELECT 1 FROM marks WHERE user_id=? AND movie_id=? AND kind=?',(uid,mid,kind))
            if exists:
                self.conn.execute('DELETE FROM marks WHERE user_id=? AND movie_id=? AND kind=?',(uid,mid,kind))
            else:
                self.conn.execute('INSERT INTO marks VALUES(?,?,?)',(uid,mid,kind))
        return not exists

    def backup(self, destination):
        with sqlite3.connect(destination) as target:
            self.conn.backup(target)

    def close(self):
        self.conn.close()
