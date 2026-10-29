import json
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY,
    added_by INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image TEXT,
    published INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    image TEXT,
    options TEXT NOT NULL DEFAULT '[]',
    correct INTEGER,
    answers TEXT NOT NULL DEFAULT '[]',
    explanation TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    sequence TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT 'question',
    message_id INTEGER,
    correct INTEGER NOT NULL DEFAULT 0,
    scored INTEGER NOT NULL DEFAULT 0,
    started_at INTEGER NOT NULL,
    finished_at INTEGER
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option INTEGER,
    answer TEXT NOT NULL,
    is_correct INTEGER,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_quiz ON questions(quiz_id, position);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id, stage);
CREATE INDEX IF NOT EXISTS idx_attempts_quiz ON attempts(quiz_id);
CREATE INDEX IF NOT EXISTS idx_responses_attempt ON responses(attempt_id);
"""

ACTIVE = ("question", "feedback")

MIGRATIONS = {
    "quizzes": {
        "single": "INTEGER NOT NULL DEFAULT 1",
        "round": "INTEGER NOT NULL DEFAULT 1",
    },
    "attempts": {
        "round": "INTEGER NOT NULL DEFAULT 1",
    },
}


def now() -> int:
    return int(time.time())


@dataclass
class Quiz:
    id: int
    title: str
    description: str
    image: str | None
    published: bool
    created_at: int
    single: bool = True
    round: int = 1
    questions: int = 0


@dataclass
class Question:
    id: int
    quiz_id: int
    position: int
    kind: str
    text: str
    image: str | None
    options: list[str]
    correct: int | None
    answers: list[str]
    explanation: str

    @property
    def is_choice(self) -> bool:
        return self.kind == "choice"

    @property
    def scored(self) -> bool:
        return self.correct is not None if self.is_choice else bool(self.answers)

    @property
    def right_answer(self) -> str | None:
        if self.is_choice:
            if self.correct is not None and self.correct < len(self.options):
                return self.options[self.correct]
            return None
        return self.answers[0] if self.answers else None


@dataclass
class Attempt:
    id: int
    user_id: int
    quiz_id: int
    sequence: list[int]
    position: int
    stage: str
    message_id: int | None
    correct: int
    scored: int
    started_at: int
    finished_at: int | None
    round: int = 1

    @property
    def current(self) -> int | None:
        if self.position < len(self.sequence):
            return self.sequence[self.position]
        return None

    @property
    def active(self) -> bool:
        return self.stage in ACTIVE


def to_quiz(row) -> Quiz:
    return Quiz(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        image=row["image"],
        published=bool(row["published"]),
        created_at=row["created_at"],
        single=bool(row["single"]),
        round=row["round"],
        questions=row["questions"] if "questions" in row.keys() else 0,
    )


def to_question(row) -> Question:
    return Question(
        id=row["id"],
        quiz_id=row["quiz_id"],
        position=row["position"],
        kind=row["kind"],
        text=row["text"],
        image=row["image"],
        options=json.loads(row["options"]),
        correct=row["correct"],
        answers=json.loads(row["answers"]),
        explanation=row["explanation"],
    )


def to_attempt(row) -> Attempt:
    return Attempt(
        id=row["id"],
        user_id=row["user_id"],
        quiz_id=row["quiz_id"],
        sequence=json.loads(row["sequence"]),
        position=row["position"],
        stage=row["stage"],
        message_id=row["message_id"],
        correct=row["correct"],
        scored=row["scored"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        round=row["round"],
    )


QUIZ_SELECT = """
SELECT q.*, (SELECT COUNT(*) FROM questions WHERE quiz_id = q.id) AS questions
FROM quizzes q
"""

QUIZ_FIELDS = {"title", "description", "image", "published", "single"}
QUESTION_FIELDS = {"kind", "text", "image", "options", "correct", "answers", "explanation"}


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self.conn.executescript(SCHEMA)
        await self.migrate()
        await self.conn.commit()

    async def migrate(self) -> None:
        for table, columns in MIGRATIONS.items():
            existing = {row["name"] for row in await self.all(f"PRAGMA table_info({table})")}
            for name, definition in columns.items():
                if name not in existing:
                    await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def one(self, sql: str, *args):
        async with self.conn.execute(sql, args) as cursor:
            return await cursor.fetchone()

    async def all(self, sql: str, *args) -> list:
        async with self.conn.execute(sql, args) as cursor:
            return list(await cursor.fetchall())

    async def run(self, sql: str, *args) -> aiosqlite.Cursor:
        cursor = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cursor

    async def scalar(self, sql: str, *args, default=0):
        row = await self.one(sql, *args)
        return row[0] if row and row[0] is not None else default

    async def upsert_user(self, user_id: int, username: str | None, name: str) -> None:
        await self.run(
            """
            INSERT INTO users (id, username, name, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username = excluded.username, name = excluded.name
            """,
            user_id, username, name, now(),
        )

    async def get_user(self, user_id: int):
        return await self.one("SELECT * FROM users WHERE id = ?", user_id)

    async def users_count(self) -> int:
        return await self.scalar("SELECT COUNT(*) FROM users")

    async def is_admin(self, user_id: int) -> bool:
        return await self.one("SELECT 1 FROM admins WHERE id = ?", user_id) is not None

    async def admins(self) -> list:
        return await self.all(
            """
            SELECT a.id, a.created_at, u.username, u.name
            FROM admins a LEFT JOIN users u ON u.id = a.id
            ORDER BY a.created_at
            """
        )

    async def add_admin(self, user_id: int, added_by: int) -> bool:
        cursor = await self.run(
            "INSERT OR IGNORE INTO admins (id, added_by, created_at) VALUES (?, ?, ?)",
            user_id, added_by, now(),
        )
        return cursor.rowcount > 0

    async def remove_admin(self, user_id: int) -> None:
        await self.run("DELETE FROM admins WHERE id = ?", user_id)

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = await self.one("SELECT value FROM settings WHERE key = ?", key)
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str | None) -> None:
        await self.run(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            key, value,
        )

    async def create_quiz(self, title: str, description: str = "", image: str | None = None, published: bool = False) -> int:
        cursor = await self.run(
            "INSERT INTO quizzes (title, description, image, published, created_at) VALUES (?, ?, ?, ?, ?)",
            title, description, image, int(published), now(),
        )
        return cursor.lastrowid

    async def get_quiz(self, quiz_id: int) -> Quiz | None:
        row = await self.one(QUIZ_SELECT + " WHERE q.id = ?", quiz_id)
        return to_quiz(row) if row else None

    async def quizzes(self, published_only: bool = False) -> list[Quiz]:
        where = " WHERE q.published = 1" if published_only else ""
        rows = await self.all(QUIZ_SELECT + where + " ORDER BY q.created_at, q.id")
        return [to_quiz(row) for row in rows]

    async def update_quiz(self, quiz_id: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in QUIZ_FIELDS}
        if not fields:
            return
        sets = ", ".join(f"{key} = ?" for key in fields)
        await self.run(f"UPDATE quizzes SET {sets} WHERE id = ?", *fields.values(), quiz_id)

    async def delete_quiz(self, quiz_id: int) -> None:
        await self.run("DELETE FROM quizzes WHERE id = ?", quiz_id)

    async def add_question(
        self,
        quiz_id: int,
        kind: str,
        text: str,
        image: str | None = None,
        options: list[str] | None = None,
        correct: int | None = None,
        answers: list[str] | None = None,
        explanation: str = "",
    ) -> int:
        position = await self.scalar("SELECT MAX(position) FROM questions WHERE quiz_id = ?", quiz_id, default=0) + 1
        cursor = await self.run(
            """
            INSERT INTO questions (quiz_id, position, kind, text, image, options, correct, answers, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            quiz_id, position, kind, text, image,
            json.dumps(options or [], ensure_ascii=False), correct,
            json.dumps(answers or [], ensure_ascii=False), explanation,
        )
        return cursor.lastrowid

    async def get_question(self, question_id: int) -> Question | None:
        row = await self.one("SELECT * FROM questions WHERE id = ?", question_id)
        return to_question(row) if row else None

    async def questions(self, quiz_id: int) -> list[Question]:
        rows = await self.all("SELECT * FROM questions WHERE quiz_id = ? ORDER BY position, id", quiz_id)
        return [to_question(row) for row in rows]

    async def update_question(self, question_id: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in QUESTION_FIELDS}
        for key in ("options", "answers"):
            if key in fields:
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        if not fields:
            return
        sets = ", ".join(f"{key} = ?" for key in fields)
        await self.run(f"UPDATE questions SET {sets} WHERE id = ?", *fields.values(), question_id)

    async def delete_question(self, question_id: int) -> None:
        await self.run("DELETE FROM questions WHERE id = ?", question_id)

    async def move_question(self, question_id: int, step: int) -> bool:
        question = await self.get_question(question_id)
        if not question:
            return False
        sign, order = ("<", "DESC") if step < 0 else (">", "ASC")
        other = await self.one(
            f"SELECT id, position FROM questions WHERE quiz_id = ? AND position {sign} ? ORDER BY position {order} LIMIT 1",
            question.quiz_id, question.position,
        )
        if not other:
            return False
        await self.conn.execute("UPDATE questions SET position = ? WHERE id = ?", (other["position"], question.id))
        await self.conn.execute("UPDATE questions SET position = ? WHERE id = ?", (question.position, other["id"]))
        await self.conn.commit()
        return True

    async def start_attempt(self, user_id: int, quiz: Quiz, sequence: list[int]) -> Attempt:
        await self.run(
            "UPDATE attempts SET stage = 'dropped' WHERE user_id = ? AND quiz_id = ? AND stage IN ('question', 'feedback')",
            user_id, quiz.id,
        )
        cursor = await self.run(
            "INSERT INTO attempts (user_id, quiz_id, sequence, round, started_at) VALUES (?, ?, ?, ?, ?)",
            user_id, quiz.id, json.dumps(sequence), quiz.round, now(),
        )
        return await self.get_attempt(cursor.lastrowid)

    async def passed(self, user_id: int, quiz: Quiz) -> list[Attempt]:
        rows = await self.all(
            "SELECT * FROM attempts WHERE user_id = ? AND quiz_id = ? AND round = ? AND stage = 'done' ORDER BY finished_at",
            user_id, quiz.id, quiz.round,
        )
        return [to_attempt(row) for row in rows]

    async def passed_count(self, quiz: Quiz) -> int:
        return await self.scalar(
            "SELECT COUNT(DISTINCT user_id) FROM attempts WHERE quiz_id = ? AND round = ? AND stage = 'done'",
            quiz.id, quiz.round,
        )

    async def reset_quiz(self, quiz_id: int) -> None:
        await self.conn.execute("UPDATE quizzes SET round = round + 1 WHERE id = ?", (quiz_id,))
        await self.conn.execute(
            "UPDATE attempts SET stage = 'dropped' WHERE quiz_id = ? AND stage IN ('question', 'feedback')",
            (quiz_id,),
        )
        await self.conn.commit()

    async def get_attempt(self, attempt_id: int) -> Attempt | None:
        row = await self.one("SELECT * FROM attempts WHERE id = ?", attempt_id)
        return to_attempt(row) if row else None

    async def active_attempt(self, user_id: int, quiz_id: int | None = None) -> Attempt | None:
        sql = "SELECT * FROM attempts WHERE user_id = ? AND stage IN ('question', 'feedback')"
        args = [user_id]
        if quiz_id is not None:
            sql += " AND quiz_id = ?"
            args.append(quiz_id)
        row = await self.one(sql + " ORDER BY COALESCE(message_id, 0) DESC, id DESC LIMIT 1", *args)
        return to_attempt(row) if row else None

    async def set_attempt_message(self, attempt_id: int, message_id: int) -> None:
        await self.run("UPDATE attempts SET message_id = ? WHERE id = ?", message_id, attempt_id)

    async def claim(self, attempt_id: int, position: int) -> bool:
        cursor = await self.run(
            "UPDATE attempts SET stage = 'feedback' WHERE id = ? AND position = ? AND stage = 'question'",
            attempt_id, position,
        )
        return cursor.rowcount > 0

    async def advance(self, attempt_id: int, position: int) -> bool:
        cursor = await self.run(
            """
            UPDATE attempts SET position = position + 1, stage = 'question'
            WHERE id = ? AND position = ? AND stage IN ('question', 'feedback')
            """,
            attempt_id, position,
        )
        return cursor.rowcount > 0

    async def finish_attempt(self, attempt_id: int) -> None:
        await self.run(
            "UPDATE attempts SET stage = 'done', finished_at = ? WHERE id = ? AND stage IN ('question', 'feedback')",
            now(), attempt_id,
        )

    async def save_response(
        self, attempt: Attempt, question: Question, answer: str, option: int | None, is_correct: bool | None
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO responses (attempt_id, question_id, option, answer, is_correct, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (attempt.id, question.id, option, answer, None if is_correct is None else int(is_correct), now()),
        )
        if is_correct is not None:
            await self.conn.execute(
                "UPDATE attempts SET correct = correct + ?, scored = scored + 1 WHERE id = ?",
                (int(is_correct), attempt.id),
            )
        await self.conn.commit()

    async def response(self, attempt_id: int, question_id: int):
        return await self.one(
            "SELECT * FROM responses WHERE attempt_id = ? AND question_id = ? ORDER BY id DESC LIMIT 1",
            attempt_id, question_id,
        )

    async def finished_attempts(self, user_id: int, quiz_id: int | None = None) -> list[Attempt]:
        sql = "SELECT * FROM attempts WHERE user_id = ? AND stage = 'done'"
        args = [user_id]
        if quiz_id is not None:
            sql += " AND quiz_id = ?"
            args.append(quiz_id)
        rows = await self.all(sql + " ORDER BY finished_at", *args)
        return [to_attempt(row) for row in rows]

    async def overview(self) -> dict:
        day_start = now() - now() % 86400
        return {
            "users": await self.users_count(),
            "quizzes": await self.scalar("SELECT COUNT(*) FROM quizzes"),
            "published": await self.scalar("SELECT COUNT(*) FROM quizzes WHERE published = 1"),
            "finished": await self.scalar("SELECT COUNT(*) FROM attempts WHERE stage = 'done'"),
            "today": await self.scalar(
                "SELECT COUNT(*) FROM attempts WHERE stage = 'done' AND finished_at >= ?", day_start
            ),
        }

    async def quiz_summary(self, quiz_id: int) -> dict:
        row = await self.one(
            """
            SELECT COUNT(*) AS runs,
                   COUNT(DISTINCT user_id) AS people,
                   AVG(CASE WHEN scored > 0 THEN correct * 1.0 / scored END) AS average
            FROM attempts WHERE quiz_id = ? AND stage = 'done'
            """,
            quiz_id,
        )
        return {"runs": row["runs"], "people": row["people"], "average": row["average"]}

    async def question_breakdown(self, quiz_id: int) -> dict[int, dict]:
        rows = await self.all(
            """
            SELECT r.question_id, r.option, r.is_correct, COUNT(*) AS amount
            FROM responses r JOIN attempts a ON a.id = r.attempt_id
            WHERE a.quiz_id = ?
            GROUP BY r.question_id, r.option, r.is_correct
            """,
            quiz_id,
        )
        result: dict[int, dict] = {}
        for row in rows:
            item = result.setdefault(row["question_id"], {"total": 0, "right": 0, "checked": 0, "options": {}})
            item["total"] += row["amount"]
            if row["is_correct"] is not None:
                item["checked"] += row["amount"]
                item["right"] += row["amount"] * row["is_correct"]
            if row["option"] is not None:
                item["options"][row["option"]] = item["options"].get(row["option"], 0) + row["amount"]
        return result

    async def export_rows(self, quiz_id: int) -> tuple[list[Question], list]:
        questions = await self.questions(quiz_id)
        attempts = await self.all(
            """
            SELECT a.*, u.username, u.name FROM attempts a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.quiz_id = ? AND EXISTS (SELECT 1 FROM responses r WHERE r.attempt_id = a.id)
            ORDER BY a.started_at
            """,
            quiz_id,
        )
        answers = await self.all(
            """
            SELECT r.attempt_id, r.question_id, r.answer, r.is_correct FROM responses r
            JOIN attempts a ON a.id = r.attempt_id WHERE a.quiz_id = ?
            """,
            quiz_id,
        )
        by_attempt: dict[int, dict[int, tuple[str, int | None]]] = {}
        for row in answers:
            by_attempt.setdefault(row["attempt_id"], {})[row["question_id"]] = (row["answer"], row["is_correct"])
        return questions, [(row, by_attempt.get(row["id"], {})) for row in attempts]
