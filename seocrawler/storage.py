"""SQLite: очередь, страницы, связи. Обход можно продолжить после сбоя."""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    depth INTEGER,
    internal INTEGER,
    kind TEXT,              -- page / resource / external
    state TEXT DEFAULT 'queued',  -- queued / done / skipped
    skip_reason TEXT,
    found_on TEXT
);
CREATE INDEX IF NOT EXISTS urls_state ON urls(state, id);
CREATE INDEX IF NOT EXISTS urls_queue ON urls(state, internal, kind, id);
CREATE TABLE IF NOT EXISTS rel_links (raw TEXT, dst TEXT, anchor TEXT, src TEXT, PRIMARY KEY (raw, dst)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    status INTEGER, reason TEXT, error TEXT,
    content_type TEXT, size INTEGER, elapsed REAL,
    location TEXT, redirect_type TEXT,
    title TEXT, title_count INTEGER,
    description TEXT, description_count INTEGER,
    h1 TEXT, h1_count INTEGER, h2_count INTEGER,
    canonical TEXT, canonical_count INTEGER, canonical_header TEXT,
    meta_robots TEXT, x_robots TEXT,
    indexable INTEGER, indexability TEXT,
    word_count INTEGER, content_hash TEXT, text_sample TEXT,
    encoding TEXT, encoding_source TEXT, bad_chars INTEGER,
    lang TEXT, hreflang TEXT,
    last_modified TEXT, content_encoding TEXT,
    images_no_alt INTEGER, outlinks_internal INTEGER, outlinks_external INTEGER,
    truncated INTEGER, ssl_note TEXT
);
CREATE TABLE IF NOT EXISTS param_links (src TEXT, raw TEXT, cleaned TEXT, removed TEXT);
CREATE TABLE IF NOT EXISTS images (page TEXT, src TEXT, alt TEXT, has_size INTEGER);
CREATE INDEX IF NOT EXISTS images_src ON images(src);
CREATE TABLE IF NOT EXISTS resources (page TEXT, src TEXT, type TEXT);
CREATE INDEX IF NOT EXISTS resources_src ON resources(src);
CREATE TABLE IF NOT EXISTS img_display (page TEXT, src TEXT, w INTEGER, h INTEGER);
"""



EXTRA_COLS = [
    ("ssl_note", "TEXT"),
    # режим JavaScript: исходный HTML против страницы после скриптов
    ("js_error", "TEXT"), ("js_time", "REAL"), ("js_blocked", "TEXT"), ("js_errors", "INTEGER"),
    ("js_redirect", "TEXT"), ("raw_title", "TEXT"), ("raw_description", "TEXT"), ("raw_h1", "TEXT"),
    ("raw_canonical", "TEXT"), ("raw_robots", "TEXT"), ("raw_words", "INTEGER"),
    ("raw_links", "INTEGER"), ("js_links", "INTEGER"), ("js_only_links_count", "INTEGER"),
    ("js_only_links", "TEXT"), ("js_text_sample", "TEXT"), ("minhash", "TEXT"),
    # картинки: формат и настоящие размеры из заголовка файла
    ("img_format", "TEXT"), ("img_width", "INTEGER"), ("img_height", "INTEGER"), ("size_measured", "INTEGER"),
    # версия 6: мобильная версия, соцсети, микроразметка, ошибки HTML, текст без меню и подвала
    ("viewport", "TEXT"), ("keywords", "TEXT"), ("og", "TEXT"), ("schema_types", "TEXT"), ("schema_errors", "INTEGER"),
    ("html_multi", "TEXT"), ("dup_ids", "TEXT"), ("head_break", "TEXT"), ("after_break", "TEXT"),
    ("content_words", "INTEGER"),
    ("ttfb", "REAL"), ("ttfb_recheck", "REAL"),  # время до ответа; повторный замер после обхода
    ("blocks", "BLOB"),
    ("cache_control", "TEXT"),  # картинки, стили, скрипты: Cache-Control (или Expires); «—» — ничего нет
    ("schema_info", "TEXT"),  # что заполнено в разметке товара, крошек, организации (JSON) — версия 7.1
    ("counters", "TEXT"),  # счётчики Метрики / Google Analytics / GTM на странице (JSON) — версия 7.1
    ("shop", "TEXT"),  # цены, наличие, кнопки, формы — для «Что мешает покупать» (seocrawler/shop.py)
    ("extract", "TEXT"),  # «Свои данные со страниц» по правилам (JSON {правило: [значения]}) - seocrawler/extract.py
    ("hidden_links", "TEXT"),  # ссылки на чужие сайты в спрятанном блоке (JSON [[адрес, текст]]) - версия 7.4
    ("calltrack", "TEXT"),  # коллтрекинг: телефоны в HTML и после JavaScript, сервис (JSON) - seocrawler/calltrack.py
    ("contacts", "TEXT"),  # телефоны и адреса со страницы (JSON) — для проверки местного SEO  # текст по блокам (zlib) — для вычитания шаблона сайта
]
# Ссылки (с версии 6) хранятся номерами: адрес и текст ссылки записываются один раз в strs,
# а в link_rows — только номера. Иначе сквозное меню на 8 тыс. страниц раздувало базу до 6 ГБ.
# Для остального кода есть представление links с прежними колонками.
LINKS_V6 = """
CREATE TABLE IF NOT EXISTS strs (id INTEGER PRIMARY KEY, s TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS link_rows (
    src INTEGER, dst INTEGER, anchor INTEGER, nofollow INTEGER, kind TEXT, internal INTEGER
);
CREATE INDEX IF NOT EXISTS link_rows_dst ON link_rows(dst);
CREATE INDEX IF NOT EXISTS link_rows_src ON link_rows(src);
CREATE VIEW IF NOT EXISTS links AS
    SELECT s.s AS src, d.s AS dst, NULL AS dst_raw, a.s AS anchor, l.nofollow, l.kind, l.internal
    FROM link_rows l JOIN strs s ON s.id=l.src JOIN strs d ON d.id=l.dst LEFT JOIN strs a ON a.id=l.anchor;
"""
# Старые базы (до версии 6): обычная таблица links с текстом — читаются как раньше.
LINKS_OLD = """
CREATE TABLE IF NOT EXISTS links (
    src TEXT, dst TEXT, dst_raw TEXT, anchor TEXT, nofollow INTEGER, kind TEXT, internal INTEGER
);
CREATE INDEX IF NOT EXISTS links_dst ON links(dst);
CREATE INDEX IF NOT EXISTS links_src ON links(src);
"""

IMAGE_EXTRA = [("loading", "TEXT"), ("in_picture", "INTEGER"), ("srcset", "INTEGER")]


class Store:
    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        kind = self.db.execute("SELECT type FROM sqlite_master WHERE name='links'").fetchone()
        has_urls = self.db.execute("SELECT 1 FROM urls LIMIT 1").fetchone()
        # старая база с таблицей links — оставляем как есть; новая — компактное хранение
        self.legacy_links = bool(kind and kind[0] == "table") or (not kind and has_urls is not None)
        self.db.executescript(LINKS_OLD if self.legacy_links else LINKS_V6)
        self._sid = {}
        self.page_cols = [r[1] for r in self.db.execute("PRAGMA table_info(pages)")]
        for col, typ in EXTRA_COLS:  # колонки, добавленные в новых версиях
            if col not in self.page_cols:
                self.db.execute(f"ALTER TABLE pages ADD COLUMN {col} {typ}")
                self.page_cols.append(col)
        self.db.execute("CREATE TABLE IF NOT EXISTS sitemap (url TEXT PRIMARY KEY)")
        img_cols = [r[1] for r in self.db.execute("PRAGMA table_info(images)")]
        for col, typ in IMAGE_EXTRA:
            if col not in img_cols:
                self.db.execute(f"ALTER TABLE images ADD COLUMN {col} {typ}")

    # --- meta
    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def get_meta(self, key, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    # --- очередь
    def enqueue(self, url, depth, internal, kind, found_on, state="queued", skip_reason=None):
        """True, если URL новый (его ещё не видели)."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO urls(url, depth, internal, kind, state, skip_reason, found_on) "
            "VALUES (?,?,?,?,?,?,?)", (url, depth, int(internal), kind, state, skip_reason, found_on))
        return cur.rowcount == 1

    def seen(self, url):
        return self.db.execute("SELECT 1 FROM urls WHERE url=?", (url,)).fetchone() is not None

    def in_sitemap(self, url):
        return self.db.execute("SELECT 1 FROM sitemap WHERE url=?", (url,)).fetchone() is not None

    def next_batch(self, n, pages_allowed=True):
        """Следующие адреса из очереди: (страницы сайта, остальное — картинки, внешние ссылки, sitemap).
        Порознь, чтобы страницы не ждали за картинками: на zoozavr.ru у каждого товара десятки фото,
        и число страниц по полчаса стояло, пока проверялись фото, найденные раньше следующей страницы.
        Если лимит страниц исчерпан — страниц не даём (картинки и ссылки в лимит не считаются)."""
        q = "SELECT url, depth, internal, kind FROM urls WHERE state='queued' AND {} ORDER BY id LIMIT ?"
        pages = self.db.execute(q.format("internal=1 AND kind='page'"), (n,)).fetchall() if pages_allowed else []
        other = self.db.execute(q.format("NOT (internal=1 AND kind='page')"), (n,)).fetchall()
        return pages, other

    def progress(self):
        """Сколько чего проверено и сколько ждёт: для строки прогресса."""
        out = {}
        for kind, internal, state, n in self.db.execute(
                "SELECT kind, internal, state, COUNT(*) FROM urls GROUP BY kind, internal, state"):
            # картинки и файлы на других сайтах (CDN) — отдельно от внешних ссылок
            key = kind if internal else ("ext_file" if kind == "resource" else "external")
            out.setdefault(key, {}).setdefault(state, 0)
            out[key][state] += n
        return out

    def mark(self, url, state, reason=None):
        self.db.execute("UPDATE urls SET state=?, skip_reason=COALESCE(?, skip_reason) WHERE url=?",
                        (state, reason, url))

    def count(self, where="1=1"):
        return self.db.execute(f"SELECT COUNT(*) FROM urls WHERE {where}").fetchone()[0]

    def save_page(self, row: dict):
        cols = [c for c in self.page_cols if c in row]
        self.db.execute(f"INSERT OR REPLACE INTO pages({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [row[c] for c in cols])

    def str_id(self, s):
        if s is None or s == "":
            return None
        i = self._sid.get(s)
        if i is None:
            self.db.execute("INSERT OR IGNORE INTO strs(s) VALUES (?)", (s,))
            i = self.db.execute("SELECT id FROM strs WHERE s=?", (s,)).fetchone()[0]
            if len(self._sid) > 500_000:
                self._sid.clear()
            self._sid[s] = i
        return i

    def add_rel_links(self, rows: list) -> None:
        """Ссылки страницы без «/» в начале: (запись, куда привела, текст, страница); одна строка на пару."""
        self.db.executemany("INSERT OR IGNORE INTO rel_links(raw, dst, anchor, src) VALUES (?,?,?,?)", rows)

    def add_links(self, rows):
        """rows: (src, dst, dst_raw, anchor, nofollow, kind, internal). Одинаковые ссылки с одной страницы
        (меню вверху и то же меню в подвале) записываются один раз."""
        seen, uniq = set(), []
        for r in rows:
            k = (r[1], r[3], r[4], r[5])
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        if self.legacy_links:
            self.db.executemany("INSERT INTO links VALUES (?,?,?,?,?,?,?)", uniq)
            return
        sid = self.str_id
        self.db.executemany("INSERT INTO link_rows VALUES (?,?,?,?,?,?)",
                            [(sid(r[0]), sid(r[1]), sid(r[3]), r[4], r[5], r[6]) for r in uniq])

    def forget_page_data(self, url):
        """Убрать всё, что записано со страницы (ссылки, картинки, файлы) — перед повторной загрузкой."""
        if self.legacy_links:
            self.db.execute("DELETE FROM links WHERE src=?", (url,))
        else:
            r = self.db.execute("SELECT id FROM strs WHERE s=?", (url,)).fetchone()
            if r:
                self.db.execute("DELETE FROM link_rows WHERE src=?", (r[0],))
        for t in ("images", "resources", "img_display"):
            self.db.execute(f"DELETE FROM {t} WHERE page=?", (url,))
        self.db.execute("DELETE FROM param_links WHERE src=?", (url,))

    def add_param_links(self, rows):
        self.db.executemany("INSERT INTO param_links VALUES (?,?,?,?)", rows)

    def add_images(self, rows):
        rows = list(dict.fromkeys(rows))  # одна и та же картинка на странице — одной строкой
        self.db.executemany("INSERT INTO images(page, src, alt, has_size, loading, in_picture, srcset) "
                            "VALUES (?,?,?,?,?,?,?)", rows)

    def add_resources(self, rows):
        rows = list(dict.fromkeys(rows))
        self.db.executemany("INSERT INTO resources VALUES (?,?,?)", rows)

    def add_img_display(self, rows):
        self.db.executemany("INSERT INTO img_display VALUES (?,?,?,?)", rows)

    def commit(self):
        self.db.commit()
