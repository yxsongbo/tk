import json
import sqlite3
from pathlib import Path
import pytest

import app.main as main

SCHEMA = Path(main.BASE_DIR) / "database" / "schema.sql"


def make_conn():
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.executescript(SCHEMA.read_text())
    # ensure extra tables
    cursor = raw.cursor()
    main.ensure_exam_questions_table(cursor)
    main.ensure_favorite_tables(cursor)
    raw.commit()
    return main._SQLiteCompatConn(raw)


def test_favorites_unpracticed_incorrect():
    conn = make_conn()
    cursor = conn._conn.cursor()

    # create a student
    cursor.execute("INSERT INTO students (exam_number, class_number, student_number, name, subject_group) VALUES (?,?,?,?,?)",
                   ("e1", 1, 1, "Alice", 1))
    student_id = cursor.lastrowid

    # insert exam questions
    cursor.execute(
        "INSERT INTO exam_questions (exam_filename, id, type, question, score, explanation, image, correct_answer, options) VALUES (?,?,?,?,?,?,?,?,?)",
        ("exam1", "q1", "choice", "Q1", 2.5, "", "", "0", json.dumps([{"text":"A"}, {"text":"B"}]))
    )
    cursor.execute(
        "INSERT INTO exam_questions (exam_filename, id, type, question, score, explanation, image, correct_answer, options) VALUES (?,?,?,?,?,?,?,?,?)",
        ("exam1", "q2", "choice", "Q2", 2.5, "", "", "1", json.dumps([{"text":"C"}, {"text":"D"}]))
    )

    # mark q1 as answered incorrect
    # create a session
    cursor.execute("INSERT INTO sessions (student_id, start_time, status, exam_filename) VALUES (?,?,?,?)",
                   (student_id, "now", "completed", "exam1"))
    session_id = cursor.lastrowid
    cursor.execute("INSERT INTO answers (session_id, student_id, question_id, answer, is_correct, score, answer_time, created_at, exam_filename) VALUES (?,?,?,?,?,?,?,?,?)",
                   (session_id, student_id, "q1", "1", 0, 0, 10, "now", "exam1"))

    # add favorite q2
    cursor.execute("INSERT INTO student_favorites (student_id, question_id, exam_filename, question_text) VALUES (?,?,?,?)",
                   (student_id, "q2", "exam1", "Q2"))
    conn._conn.commit()

    # favorites mode
    res = main.get_practice_questions(student_id=student_id, mode="favorites", exam_filename=None, conn=conn)
    assert res["mode"] == "favorites"
    assert len(res["questions"]) == 1
    assert res["questions"][0]["id"] == "q2"

    # unpracticed mode
    res2 = main.get_practice_questions(student_id=student_id, mode="unpracticed", exam_filename="exam1", conn=conn)
    ids = {q["id"] for q in res2["questions"]}
    assert "q2" in ids and "q1" not in ids

    # incorrect mode
    res3 = main.get_practice_questions(student_id=student_id, mode="incorrect", exam_filename="exam1", conn=conn)
    ids3 = {q["id"] for q in res3["questions"]}
    assert "q1" in ids3 and "q2" not in ids3
