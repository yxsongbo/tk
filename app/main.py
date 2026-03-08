#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
练习系统后端API
支持100人同时在线练习
技术栈: FastAPI + SQLite
"""

import json
import ast
import re
import sqlite3
from datetime import datetime
from typing import Any, List, Optional
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
import uvicorn

# 项目路径
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
EXAMS_DIR = BASE_DIR / "exams"

# 数据库路径
DATABASE = str(BASE_DIR / "practice.db")


def normalize_fill_answer(answer: str) -> str:
    """统一填空答案格式：去首尾空白、去全角空格、忽略中间空格。"""
    return str(answer).strip().replace("\u3000", "").replace(" ", "")


def build_fill_answer_variants(answer: str) -> set[str]:
    """从标准答案中提取可接受答案（支持“或”前后写法）。"""
    raw = str(answer).strip()
    if not raw:
        return set()

    variants = {normalize_fill_answer(raw)}

    normalized_brackets = raw.replace("（", "(").replace("）", ")")

    # 兼容：A（或B）/ A(或B) / A或B / A，或B / A,或B
    if "或" in normalized_brackets:
        parts = re.split(r"\s*[,，]?\s*或\s*", normalized_brackets)
        for part in parts:
            cleaned = part.strip().strip("()[]{}<>\"'“”‘’、，,;；")
            candidate = normalize_fill_answer(cleaned)
            if candidate:
                variants.add(candidate)

            # 兼容：字符串(str) 这种混合写法
            m = re.match(r"^(.*?)\((.*?)\)$", cleaned)
            if m:
                left = normalize_fill_answer(m.group(1))
                right = normalize_fill_answer(m.group(2))
                if left:
                    variants.add(left)
                if right:
                    variants.add(right)

    return {v for v in variants if v}


def is_fill_answer_match(student_answer: str, correct_answer: str) -> bool:
    """填空匹配：含“或”时，允许匹配“或”前后内容（含近似包含）。"""
    student = normalize_fill_answer(student_answer)
    if not student:
        return False

    raw = str(correct_answer or "").strip()
    variants = build_fill_answer_variants(raw)
    if not variants:
        return False

    if student in variants:
        return True

    # 仅在含“或”时放宽匹配：前后内容的包含关系也判对
    if "或" in raw.replace("（", "(").replace("）", ")"):
        for variant in variants:
            if len(student) >= 2 and len(variant) >= 2 and (
                student in variant or variant in student
            ):
                return True

    return False


def _coerce_str_list(value: Any) -> list[str]:
    """把值统一转换为字符串数组（去掉空值）。"""
    if value is None:
        return []
    if isinstance(value, list):
        values = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                values.append(text)
        return values
    text = str(value).strip()
    return [text] if text else []


def _coerce_image_list(value: Any) -> list[str]:
    """把单图/多图字段统一为字符串数组。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except Exception:
                pass
        return [raw]
    text = str(value).strip()
    return [text] if text else []


def _normalize_fill_blank_item(item: Any) -> dict:
    """标准化填空每一空的结构。"""
    if isinstance(item, dict):
        answers = _coerce_str_list(item.get("answers"))
        images = _coerce_image_list(item.get("images"))
        if not images:
            images = _coerce_image_list(item.get("image"))
        label = item.get("label")
        label_text = str(label).strip() if label is not None else None
        if label_text == "":
            label_text = None
        return {"answers": answers, "images": images, "label": label_text}

    if isinstance(item, list):
        return {"answers": _coerce_str_list(item), "images": [], "label": None}

    return {"answers": _coerce_str_list(item), "images": [], "label": None}


def parse_fill_blanks(raw: Any) -> list[dict]:
    """
    解析填空答案，兼容多种历史格式：
    1) JSON数组/对象字符串
    2) Python 字面量字符串（旧数据）
    3) 逗号分隔字符串
    """
    if raw is None:
        return []

    parsed: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []

        parsed = text
        parse_candidates: list[str] = []
        if text.startswith("[") or text.startswith("{"):
            parse_candidates.append(text)
        parse_candidates.append(text)
        parse_candidates.append(f"[{text}]")

        for candidate in parse_candidates:
            try:
                parsed = json.loads(candidate)
                break
            except Exception:
                try:
                    parsed = ast.literal_eval(candidate)
                    break
                except Exception:
                    parsed = text

        if isinstance(parsed, str):
            parts = [
                item.strip()
                for item in text.replace("，", ",").split(",")
                if item.strip()
            ]
            return [
                {"answers": [part], "images": [], "label": None} for part in parts
            ]

    if isinstance(parsed, dict):
        if isinstance(parsed.get("blanks"), list):
            parsed = parsed.get("blanks")
        elif isinstance(parsed.get("answers"), list):
            parsed = parsed.get("answers")
        else:
            return []

    if isinstance(parsed, list):
        blanks = [_normalize_fill_blank_item(item) for item in parsed]
        return [
            blank
            for blank in blanks
            if blank["answers"] or blank["images"] or blank["label"]
        ]

    return [_normalize_fill_blank_item(parsed)]


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    """为已有表补充字段（若不存在）。"""
    cursor.execute(f"PRAGMA table_info({table})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column not in existing_columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def extract_correct_answer(question_data: dict) -> str | int | None:
    """兼容不同试卷格式的答案字段。"""
    question_type = str(question_data.get("type", "")).strip()

    if question_type == "fill":
        fill_blanks = parse_fill_blanks(question_data.get("answers"))
        if not fill_blanks:
            fill_blanks = parse_fill_blanks(question_data.get("correctAnswer"))
        if fill_blanks:
            return json.dumps(fill_blanks, ensure_ascii=False)
        return None

    correct_answer = question_data.get("correctAnswer")
    if correct_answer is None and "answers" in question_data:
        answers = question_data.get("answers", [])
        if answers:
            all_answers = []
            for answer_group in answers:
                if isinstance(answer_group, list):
                    all_answers.extend([str(a) for a in answer_group if a is not None and a != ""])
                elif answer_group is not None and answer_group != "":
                    all_answers.append(str(answer_group))
            correct_answer = ",".join(all_answers) if all_answers else None
    return correct_answer


def normalize_image_field(image_value):
    """兼容单图/多图：数据库中 image 可能是字符串或 JSON 数组字符串。"""
    if image_value is None:
        return None
    if isinstance(image_value, list):
        return [str(v) for v in image_value if v]
    if not isinstance(image_value, str):
        return str(image_value)

    raw = image_value.strip()
    if not raw:
        return None

    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except Exception:
            pass
    return raw


def list_exam_files() -> list[Path]:
    """列出可用试卷文件（根目录 + exams 子目录）。"""
    EXAMS_DIR.mkdir(parents=True, exist_ok=True)
    files_by_name: dict[str, Path] = {}

    for exam_path in sorted(BASE_DIR.glob("*.json")):
        files_by_name[exam_path.name] = exam_path
    for exam_path in sorted(EXAMS_DIR.glob("*.json")):
        files_by_name[exam_path.name] = exam_path

    return [files_by_name[name] for name in sorted(files_by_name.keys())]


def resolve_exam_path(filename: str) -> Path | None:
    """按文件名解析试卷路径。"""
    safe_name = Path(filename).name
    for exam_path in list_exam_files():
        if exam_path.name == safe_name:
            return exam_path
    return None


def load_exam_json(exam_path: Path) -> dict:
    """读取并校验试卷 JSON。"""
    try:
        with open(exam_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取试卷失败: {e}") from e

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="试卷格式错误：questions 必须为非空数组")
    return data


def set_current_exam(conn: sqlite3.Connection, filename: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('current_exam', ?, datetime('now'))",
        (filename,),
    )


def get_current_exam_name(conn: sqlite3.Connection) -> str | None:
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'current_exam'")
    row = cursor.fetchone()
    if row and row["value"]:
        return row["value"]
    return None


def import_exam_into_questions(conn: sqlite3.Connection, exam_path: Path) -> dict:
    """把选中的试卷导入 questions 表（覆盖当前题库）。"""
    data = load_exam_json(exam_path)
    questions = data["questions"]
    cursor = conn.cursor()

    cursor.execute("DELETE FROM questions")

    insert_count = 0
    for q in questions:
        if not q.get("id") or not q.get("type") or not q.get("question"):
            raise HTTPException(status_code=400, detail=f"试卷题目字段缺失: {q}")

        options = (
            json.dumps(q.get("options", []), ensure_ascii=False)
            if "options" in q
            else None
        )
        correct_answer = extract_correct_answer(q)
        image_value = q.get("image")
        if not image_value and isinstance(q.get("images"), list):
            image_value = json.dumps(q.get("images", []), ensure_ascii=False)

        cursor.execute(
            """
            INSERT INTO questions (id, type, question, score, explanation, image, correct_answer, options)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(q["id"]),
                str(q["type"]),
                str(q["question"]),
                float(q.get("score", 0)),
                q.get("explanation", ""),
                image_value,
                correct_answer,
                options,
            ),
        )
        insert_count += 1

    set_current_exam(conn, exam_path.name)
    conn.commit()

    return {
        "filename": exam_path.name,
        "title": data.get("title", exam_path.name),
        "question_count": insert_count,
    }


# 数据模型
class Student(BaseModel):
    id: int
    exam_number: str
    class_number: int
    student_number: int
    name: str
    subject_group: int


class Question(BaseModel):
    id: str
    type: str
    question: str
    score: float
    explanation: Optional[str] = None
    image: Optional[str | List[str]] = None
    correct_answer: Optional[str] = None
    fill_blanks: Optional[List[dict]] = None
    options: Optional[List[dict]] = None


class AnswerRequest(BaseModel):
    student_id: int
    session_id: int
    question_id: str
    answer: str | int
    answer_time: int  # 答题用时（秒）


class SessionStart(BaseModel):
    student_id: int


class SessionResponse(BaseModel):
    id: int
    student_id: int
    start_time: str
    status: str


# 数据库连接
def get_db():
    conn = sqlite3.connect(DATABASE, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
    finally:
        conn.close()


# 初始化数据库
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    init_db()
    yield
    # 关闭时执行


app = FastAPI(title="练习系统API", lifespan=lifespan)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route(
    "/xx/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
def local_xx_api_redirect(path: str, request: Request):
    """
    本地直跑 FastAPI 时，前端会请求 /xx/api/*。
    线上由 Nginx 重写到 /api/*；本地没有 Nginx，因此这里做兼容跳转。
    """
    target = f"/api/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=307)


def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DATABASE, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")

    # 检查表是否已存在
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='students'"
    )
    if not cursor.fetchone():
        # 表不存在，执行建表脚本
        with open(BASE_DIR / "database" / "schema.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        print("数据库初始化完成")
    else:
        print("数据库已存在，跳过初始化")

    # 确保settings表存在
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )

    # 历史库结构兼容：补充试卷字段
    ensure_column(cursor, "sessions", "exam_filename", "exam_filename TEXT")
    ensure_column(cursor, "answers", "exam_filename", "exam_filename TEXT")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_exam ON sessions(exam_filename)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_answers_exam ON answers(exam_filename)"
    )
    cursor.execute(
        "UPDATE sessions SET exam_filename = '' WHERE exam_filename IS NULL"
    )
    cursor.execute("UPDATE answers SET exam_filename = '' WHERE exam_filename IS NULL")

    # 启动时保证当前试卷可用
    current_exam = get_current_exam_name(conn)
    available_exams = list_exam_files()
    if current_exam:
        current_exam_path = resolve_exam_path(current_exam)
        if current_exam_path:
            import_exam_into_questions(conn, current_exam_path)
        elif available_exams:
            import_exam_into_questions(conn, available_exams[0])
        else:
            set_current_exam(conn, "")
    elif available_exams:
        import_exam_into_questions(conn, available_exams[0])

    conn.commit()

    conn.close()


# ========== 学生相关接口 ==========


@app.get("/api/students", response_model=List[Student])
def get_students(
    class_number: Optional[int] = None, conn: sqlite3.Connection = Depends(get_db)
):
    """获取学生列表"""
    cursor = conn.cursor()
    if class_number:
        cursor.execute("SELECT * FROM students WHERE class_number = ?", (class_number,))
    else:
        cursor.execute("SELECT * FROM students ORDER BY class_number, student_number")
    rows = cursor.fetchall()
    return [Student(**dict(row)) for row in rows]


@app.get("/api/students/{student_id}", response_model=Student)
def get_student(student_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """获取单个学生信息"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="学生不存在")
    return Student(**dict(row))


# ========== 题目相关接口 ==========


@app.get("/api/questions", response_model=List[Question])
def get_questions(
    type: Optional[str] = None, conn: sqlite3.Connection = Depends(get_db)
):
    """获取题目列表"""
    try:
        cursor = conn.cursor()
        if type:
            cursor.execute("SELECT * FROM questions WHERE type = ?", (type,))
        else:
            cursor.execute("SELECT * FROM questions ORDER BY id")
        rows = cursor.fetchall()

        questions = []
        for row in rows:
            q = dict(row)
            if q["options"]:
                q["options"] = json.loads(q["options"])
            q["image"] = normalize_image_field(q.get("image"))
            if q.get("correct_answer") is not None:
                q["correct_answer"] = str(q["correct_answer"])
            if q.get("type") == "fill":
                q["fill_blanks"] = parse_fill_blanks(q.get("correct_answer"))
            questions.append(Question(**q))
        return questions
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/questions/{question_id}", response_model=Question)
def get_question(question_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """获取单道题目"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="题目不存在")

    q = dict(row)
    if q["options"]:
        q["options"] = json.loads(q["options"])
    q["image"] = normalize_image_field(q.get("image"))
    if q.get("correct_answer") is not None:
        q["correct_answer"] = str(q["correct_answer"])
    if q.get("type") == "fill":
        q["fill_blanks"] = parse_fill_blanks(q.get("correct_answer"))
    return Question(**q)


# ========== 练习会话接口 ==========


@app.post("/api/sessions/start", response_model=SessionResponse)
def start_session(data: SessionStart, conn: sqlite3.Connection = Depends(get_db)):
    """开始练习会话"""
    cursor = conn.cursor()
    current_exam = get_current_exam_name(conn)
    if not current_exam:
        raise HTTPException(status_code=400, detail="当前无可用试卷，请先在教师端导入并切换试卷")
    cursor.execute("SELECT COUNT(*) FROM questions")
    if (cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=400, detail="当前试卷题库为空，请先切换试卷")

    # 检查是否有进行中的会话
    cursor.execute(
        "SELECT id FROM sessions WHERE student_id = ? AND status = 'active'",
        (data.student_id,),
    )
    existing = cursor.fetchone()
    if existing:
        # 结束之前的会话
        cursor.execute(
            "UPDATE sessions SET status = 'abandoned', end_time = ? WHERE id = ?",
            (datetime.now(), existing["id"]),
        )

    # 创建新会话
    cursor.execute(
        "INSERT INTO sessions (student_id, start_time, status, exam_filename) VALUES (?, ?, 'active', ?)",
        (data.student_id, datetime.now(), current_exam),
    )
    conn.commit()

    session_id = cursor.lastrowid
    return SessionResponse(
        id=session_id,
        student_id=data.student_id,
        start_time=datetime.now().isoformat(),
        status="active",
    )


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """结束练习会话"""
    cursor = conn.cursor()

    # 计算总分
    cursor.execute("SELECT SUM(score) FROM answers WHERE session_id = ?", (session_id,))
    total_score = cursor.fetchone()[0] or 0

    cursor.execute(
        "UPDATE sessions SET end_time = ?, total_score = ?, status = 'completed' WHERE id = ?",
        (datetime.now(), total_score, session_id),
    )
    conn.commit()

    return {"message": "练习已结束", "total_score": total_score}


# ========== 答题接口 ==========


@app.post("/api/answers/submit")
def submit_answer(data: AnswerRequest, conn: sqlite3.Connection = Depends(get_db)):
    """提交答案"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, exam_filename FROM sessions WHERE id = ? AND student_id = ?",
        (data.session_id, data.student_id),
    )
    session = cursor.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["status"] != "active":
        raise HTTPException(status_code=400, detail="会话已结束，不能继续答题")

    session_exam = session["exam_filename"] or get_current_exam_name(conn)
    current_exam = get_current_exam_name(conn)
    if session_exam and current_exam and session_exam != current_exam:
        raise HTTPException(status_code=409, detail="当前试卷已变更，请重新开始考试")

    # 获取题目正确答案
    cursor.execute(
        "SELECT correct_answer, score, type FROM questions WHERE id = ?",
        (data.question_id,),
    )
    question = cursor.fetchone()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 判断答案是否正确
    # 填空题：每个空单独评分
    if question["type"] == "fill":
        fill_blanks = parse_fill_blanks(question["correct_answer"])
        blank_count = len(fill_blanks)
        student_answers = str(data.answer).split("|||")
        correct_count = 0

        if blank_count > 0:
            score_per_blank = question["score"] / blank_count
            for i, blank in enumerate(fill_blanks):
                student_answer = student_answers[i] if i < len(student_answers) else ""
                if any(
                    is_fill_answer_match(student_answer, raw_answer)
                    for raw_answer in blank.get("answers", [])
                ):
                    correct_count += 1

            score = round(score_per_blank * correct_count, 2)
            is_correct = correct_count == blank_count
        else:
            score = 0
            is_correct = False
    else:
        # 选择题：整体判定
        correct_answers = str(question["correct_answer"]).replace("，", ",").split(",")
        student_answer = str(data.answer).strip()
        is_correct = any(
            correct.strip() == student_answer for correct in correct_answers
        )
        score = question["score"] if is_correct else 0

    # 保存或更新答案
    cursor.execute(
        """
        INSERT OR REPLACE INTO answers 
        (session_id, student_id, question_id, answer, is_correct, score, answer_time, created_at, exam_filename)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.session_id,
            data.student_id,
            data.question_id,
            data.answer,
            is_correct,
            score,
            data.answer_time,
            datetime.now(),
            session_exam or "",
        ),
    )
    conn.commit()

    return {
        "is_correct": is_correct,
        "score": score,
        "correct_answer": question["correct_answer"],
        "correct_count": correct_count if question["type"] == "fill" else None,
        "blank_count": blank_count if question["type"] == "fill" else None,
    }


# ========== 试卷管理接口 ==========


@app.get("/api/exams/list")
def get_exam_list(conn: sqlite3.Connection = Depends(get_db)):
    """获取可用的试卷列表"""
    exams = []
    for exam_path in list_exam_files():
        try:
            data = load_exam_json(exam_path)
            exams.append(
                {
                    "filename": exam_path.name,
                    "title": data.get("title", exam_path.name),
                    "question_count": len(data.get("questions", [])),
                }
            )
        except Exception:
            pass

    return exams


@app.get("/api/exams/current")
def get_current_exam(conn: sqlite3.Connection = Depends(get_db)):
    """获取当前使用的试卷"""
    current_exam = get_current_exam_name(conn)
    return {"current_exam": current_exam}


class ExamSwitch(BaseModel):
    filename: str


@app.post("/api/exams/switch")
def switch_exam(data: ExamSwitch, conn: sqlite3.Connection = Depends(get_db)):
    """切换当前使用的试卷"""
    filename = Path(data.filename).name
    exam_path = resolve_exam_path(filename)
    if not exam_path:
        raise HTTPException(status_code=404, detail="试卷文件不存在")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
    active_count = cursor.fetchone()[0] or 0
    if active_count > 0:
        cursor.execute(
            "UPDATE sessions SET status = 'abandoned', end_time = ? WHERE status = 'active'",
            (datetime.now(),),
        )

    import_result = import_exam_into_questions(conn, exam_path)
    return {
        "message": "试卷切换成功",
        "current_exam": import_result["filename"],
        "question_count": import_result["question_count"],
        "abandoned_sessions": active_count,
    }


@app.post("/api/exams/upload")
async def upload_exam(
    file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)
):
    """上传新的试卷 JSON 文件。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    safe_name = Path(file.filename).name
    if not safe_name.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 JSON 试卷文件")

    EXAMS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = EXAMS_DIR / safe_name
    existed = target_path.exists()

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}") from e

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="试卷格式错误：questions 必须为非空数组")

    with open(target_path, "wb") as f:
        f.write(content)

    current_exam = get_current_exam_name(conn)
    abandoned_sessions = 0
    synced_to_db = False
    if current_exam == safe_name:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
        abandoned_sessions = cursor.fetchone()[0] or 0
        if abandoned_sessions > 0:
            cursor.execute(
                "UPDATE sessions SET status = 'abandoned', end_time = ? WHERE status = 'active'",
                (datetime.now(),),
            )
            conn.commit()

        # 当前试卷被同名覆盖后，立即重导入题库，保证数据库与文件一致
        import_exam_into_questions(conn, target_path)
        synced_to_db = True

    if existed and synced_to_db:
        message = "同名试卷已覆盖，且已同步更新当前考试题库"
    elif existed:
        message = "同名试卷已覆盖"
    else:
        message = "试卷上传成功"

    return {
        "message": message,
        "filename": target_path.name,
        "title": data.get("title", target_path.name),
        "question_count": len(questions),
        "overwritten": existed,
        "synced_to_db": synced_to_db,
        "abandoned_sessions": abandoned_sessions,
    }


# ========== 统计分析接口（核心功能） ==========


@app.get("/api/analysis/question/{question_id}")
def get_question_analysis(question_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """
    获取某道题目的答题情况分析
    包括：哪些学生答了、答案是什么、是否正确、用时等
    """
    cursor = conn.cursor()
    current_exam = get_current_exam_name(conn) or ""

    # 获取题目信息
    cursor.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
    question = cursor.fetchone()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 获取所有答题记录
    cursor.execute(
        """
        SELECT 
            s.name,
            s.class_number,
            s.student_number,
            a.answer,
            a.is_correct,
            a.score,
            a.answer_time,
            a.created_at
        FROM answers a
        JOIN students s ON a.student_id = s.id
        WHERE a.question_id = ? AND a.exam_filename = ?
        ORDER BY a.created_at DESC
        """,
        (question_id, current_exam),
    )
    answers = [dict(row) for row in cursor.fetchall()]

    # 统计信息
    total = len(answers)
    correct = sum(1 for a in answers if a["is_correct"])
    wrong = total - correct
    correct_rate = round(100.0 * correct / total, 2) if total > 0 else 0

    # 各选项选择人数统计（选择题）
    option_stats = {}
    if question["type"] == "choice":
        for ans in answers:
            opt = ans["answer"]
            option_stats[opt] = option_stats.get(opt, 0) + 1

    return {
        "question": {
            "id": question["id"],
            "type": question["type"],
            "content": question["question"],
            "correct_answer": question["correct_answer"],
        },
        "statistics": {
            "total_attempts": total,
            "correct_count": correct,
            "wrong_count": wrong,
            "correct_rate": correct_rate,
            "option_distribution": option_stats,
        },
        "answers": answers,
    }


@app.get("/api/analysis/student/{student_id}")
def get_student_analysis(student_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """获取某个学生的答题分析"""
    cursor = conn.cursor()
    current_exam = get_current_exam_name(conn) or ""

    # 获取学生信息
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    # 获取答题统计
    cursor.execute(
        """
        SELECT 
            COUNT(*) as total_answered,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_count,
            SUM(score) as total_score,
            AVG(answer_time) as avg_time
        FROM answers
        WHERE student_id = ? AND exam_filename = ?
        """,
        (student_id, current_exam),
    )
    stats = dict(cursor.fetchone())

    # 获取每道题的答题情况
    cursor.execute(
        """
        SELECT 
            q.id,
            q.question,
            q.type,
            a.answer,
            a.is_correct,
            a.score,
            a.answer_time
        FROM answers a
        JOIN questions q ON a.question_id = q.id
        WHERE a.student_id = ? AND a.exam_filename = ?
        ORDER BY a.created_at DESC
        """,
        (student_id, current_exam),
    )
    details = [dict(row) for row in cursor.fetchall()]

    return {
        "student": {
            "id": student["id"],
            "name": student["name"],
            "class": student["class_number"],
            "exam_number": student["exam_number"],
        },
        "statistics": stats,
        "answers": details,
    }


@app.get("/api/analysis/overview")
def get_overview(conn: sqlite3.Connection = Depends(get_db)):
    """获取整体统计概览"""
    cursor = conn.cursor()
    current_exam = get_current_exam_name(conn) or ""

    # 总参与人数
    cursor.execute(
        "SELECT COUNT(DISTINCT student_id) FROM answers WHERE exam_filename = ?",
        (current_exam,),
    )
    total_students = cursor.fetchone()[0]

    # 总答题次数
    cursor.execute(
        "SELECT COUNT(*) FROM answers WHERE exam_filename = ?",
        (current_exam,),
    )
    total_answers = cursor.fetchone()[0]

    # 每道题的统计
    cursor.execute(
        """
        SELECT 
            q.id,
            q.question,
            COUNT(a.id) as attempt_count,
            SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) as correct_count,
            CASE
                WHEN COUNT(a.id) = 0 THEN 0
                ELSE ROUND(100.0 * SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) / COUNT(a.id), 2)
            END as correct_rate
        FROM questions q
        LEFT JOIN answers a ON q.id = a.question_id AND a.exam_filename = ?
        GROUP BY q.id
        ORDER BY correct_rate ASC
        """,
        (current_exam,),
    )
    question_stats = [dict(row) for row in cursor.fetchall()]

    return {
        "total_students": total_students,
        "total_answers": total_answers,
        "question_statistics": question_stats,
    }


# 静态文件服务
@app.get("/")
def root():
    return RedirectResponse(url="/xx", status_code=307)


@app.get("/xx")
@app.get("/xx/")
def student_entry():
    return FileResponse(APP_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/xx/js")
@app.get("/xx/js/")
def teacher_entry():
    return FileResponse(APP_DIR / "teacher.html", headers={"Cache-Control": "no-store"})


@app.get("/xx/student_detail.html")
def teacher_student_detail():
    return FileResponse(APP_DIR / "student_detail.html", headers={"Cache-Control": "no-store"})


@app.get("/styles.css")
def serve_styles():
    return FileResponse(BASE_DIR / "styles.css", headers={"Cache-Control": "no-store"})


@app.get("/xx/styles.css")
def serve_styles_xx():
    return FileResponse(BASE_DIR / "styles.css", headers={"Cache-Control": "no-store"})


@app.get("/app/{path:path}")
def serve_app(path: str):
    file_path = (APP_DIR / path).resolve()
    if APP_DIR.resolve() in file_path.parents and file_path.exists():
        headers = {"Cache-Control": "no-store"} if file_path.suffix == ".html" else None
        return FileResponse(file_path, headers=headers)
    return {"detail": "Not Found"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
