"""Local BM25 and multilingual E5 indexes for OpenCouncil evidence."""
from contextlib import closing
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import unicodedata
from urllib.request import urlopen

from filelock import FileLock

from .. import storage as db

INDEX_FILE = "athens_search.sqlite3"
MODEL_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
MODEL_URL = f"https://huggingface.co/Xenova/multilingual-e5-small/resolve/{MODEL_REVISION}/"


def normalize(text):
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).replace("ς", "σ")


def tokens(text):
    return re.findall(r"[^\W_]+", normalize(text))


def clean_text(text):
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[([^\]]+)\]\(REF:[^)]+\)", r"\1", text)
    return " ".join(re.sub(r"\(REF:[^)]+\)", "", text).split())


def passages(text):
    words = text.split()
    for start in range(0, len(words), 75):
        if start and len(words) <= start + 15:
            break
        yield " ".join(words[max(0, start - 12):start + 75])


def ensure_model():
    directory = db.DATA / "search_model"
    directory.mkdir(exist_ok=True, parents=True)
    with FileLock(str(directory / ".download.lock")):
        for name in ("tokenizer.json", "onnx/model_quantized.onnx"):
            target = directory / Path(name).name
            if not target.exists():
                print(f"Downloading the local search model ({target.name})…", flush=True)
                temp = target.with_suffix(".download")
                try:
                    with urlopen(MODEL_URL + name, timeout=60) as response, temp.open("wb") as output:
                        shutil.copyfileobj(response, output)
                    os.replace(temp, target)
                finally:
                    temp.unlink(missing_ok=True)
    return directory


@lru_cache(maxsize=1)
def encoder(directory):
    import onnxruntime as ort
    from tokenizers import Tokenizer

    for name in ("tokenizer.json", "model_quantized.onnx"):
        (directory / name).stat()
    tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=192)
    options = ort.SessionOptions()
    options.intra_op_num_threads = min(4, os.cpu_count() or 1)
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(str(directory / "model_quantized.onnx"), options,
                                   providers=["CPUExecutionProvider"])
    return tokenizer, session


def embed(texts, directory):
    import numpy as np

    tokenizer, session = encoder(directory)
    encoded = tokenizer.encode_batch(texts)
    width = max(len(item.ids) for item in encoded)
    ids = np.full((len(encoded), width), tokenizer.token_to_id("<pad>"), dtype=np.int64)
    mask = np.zeros_like(ids)
    for index, item in enumerate(encoded):
        ids[index, :len(item.ids)] = item.ids
        mask[index, :len(item.ids)] = 1
    feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
    hidden = session.run(None, {i.name: feeds[i.name] for i in session.get_inputs()})[0]
    summed = (hidden * mask[:, :, None]).sum(axis=1).astype(np.float32)
    return summed / np.maximum(np.linalg.norm(summed, axis=1, keepdims=True), 1e-12)


@lru_cache(maxsize=1)
def topic_vectors(directory, descriptions):
    return embed(["passage: " + text for text in descriptions], directory)


def topic_similarities(question, descriptions):
    (db.DATA / INDEX_FILE).stat()
    directory = db.DATA / "search_model"
    query = embed(["query: " + question], directory)[0]
    return topic_vectors(directory, descriptions) @ query


def build_index(rows):
    import numpy as np

    directory = ensure_model()
    with FileLock(str(db.DATA / INDEX_FILE) + ".build.lock"):
        entries = []
        for row in rows:
            for passage in passages(clean_text(row["text"])):
                if len(passage) >= 24:
                    entries.append((row, passage))
        if not entries:
            raise ValueError("No searchable council evidence.")

        # Similar-length inputs together keep the padded ONNX batches small.
        entries.sort(key=lambda item: len(item[1]))
        vectors = []
        batch_size = 32
        print(f"Indexing {len(entries)} OpenCouncil passages…", flush=True)
        for offset in range(0, len(entries), batch_size):
            batch = entries[offset:offset + batch_size]
            texts = [f"passage: {row['title']}\n{row['speaker']} {row['party']}\n{part}" for row, part in batch]
            vectors.append(embed(texts, directory))
            if offset and offset % 4096 == 0:
                print(f"Embedded {offset:,} passages.", flush=True)
        matrix = np.concatenate(vectors).astype(np.float16)

        fd, name = tempfile.mkstemp(dir=db.DATA, suffix=".sqlite3")
        os.close(fd)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                connection.execute("CREATE TABLE passage (id INTEGER PRIMARY KEY, date TEXT, evidence TEXT)")
                connection.execute("CREATE VIRTUAL TABLE lexical USING fts5(title, body, speaker, tokenize='unicode61')")
                connection.execute("CREATE TABLE semantic (dimensions INTEGER, vectors BLOB)")
                values = [(i, row["date"], json.dumps(dict(row, text=part), ensure_ascii=False))
                          for i, (row, part) in enumerate(entries, start=1)]
                connection.executemany("INSERT INTO passage VALUES (?, ?, ?)", values)
                connection.executemany("INSERT INTO lexical(rowid, title, body, speaker) VALUES (?, ?, ?, ?)", [
                    (i, normalize(row["title"]), normalize(part), normalize(row["speaker"] + " " + row["party"]))
                    for i, (row, part) in enumerate(entries, start=1)
                ])
                connection.execute("INSERT INTO semantic VALUES (?, ?)", (matrix.shape[1], matrix.tobytes()))
                connection.commit()
            for attempt in range(4):
                try:
                    os.replace(temporary, db.DATA / INDEX_FILE)
                    break
                except PermissionError:
                    if attempt == 3:
                        raise
                    # On Windows an active short-lived reader can hold the file open.
                    time.sleep(.25 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)
    return len(entries)


def open_index(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


@lru_cache(maxsize=1)
def semantic_matrix(path, version):
    import numpy as np

    with closing(open_index(path)) as connection:
        dimension, blob = connection.execute("SELECT * FROM semantic").fetchone()
        dates = [r[0] for r in connection.execute("SELECT date FROM passage ORDER BY id")]
    return np.frombuffer(blob, dtype=np.float16).reshape(-1, dimension).astype(np.float32), np.array(dates)


def lexical_rank(connection, terms, start, end, *, prefix=False):
    if not terms:
        return []
    suffix = "*" if prefix else ""
    query = " OR ".join('"' + term.replace('"', '""') + '"' + suffix for term in terms)
    return [row[0] for row in connection.execute(
        """SELECT lexical.rowid FROM lexical JOIN passage ON passage.id = lexical.rowid
           WHERE lexical MATCH ? AND passage.date BETWEEN ? AND ?
           ORDER BY bm25(lexical, 3.0, 1.0, 2.5), passage.date DESC LIMIT 100""",
        (query, start, end),
    )]


def candidates(question, exact_terms, topic_terms, start, end):
    import numpy as np

    path = db.DATA / INDEX_FILE
    path.stat()
    query = embed(["query: " + question], db.DATA / "search_model")[0]
    with closing(open_index(path)) as connection:
        # Hold a read transaction while pairing the matrix with its SQLite rows.
        connection.execute("BEGIN")
        exact = lexical_rank(connection, exact_terms, start, end)
        expanded = [lexical_rank(connection, terms, start, end, prefix=True)
                    for terms in topic_terms]
        matrix, dates = semantic_matrix(path, path.stat().st_mtime_ns)
        similarity = matrix @ query
        similarity[(dates < start) | (dates > end)] = -1
        top = min(100, len(similarity))
        semantic = np.argsort(similarity)[-top:][::-1]
        scores = {}
        for weight, ids in [(1.0, exact), (1.1, semantic + 1), *((.85, ids) for ids in expanded)]:
            for position, row_id in enumerate(ids, start=1):
                scores[int(row_id)] = scores.get(int(row_id), 0) + weight / (40 + position)
        ids = sorted(scores, key=scores.get, reverse=True)[:125]
        placeholders = ",".join("?" for _ in ids)
        rows = dict(connection.execute(f"SELECT id, evidence FROM passage WHERE id IN ({placeholders})", ids))
    expanded_ids = {row_id for ranking in expanded for row_id in ranking}
    return [(json.loads(rows[i]), float(similarity[i - 1]), i in exact, i in expanded_ids)
            for i in ids if i in rows and similarity[i - 1] >= 0]
