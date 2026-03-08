# AGENTS.md - Coding Guidelines for Educational Practice System

## Project Overview

This is a FastAPI-based educational practice system for high school IT academic proficiency tests. The system supports 100 concurrent users and includes:

- **Backend**: FastAPI + SQLite
- **Frontend**: Static HTML with JavaScript
- **Data**: Student records (Excel), exam questions (JSON)
- **Database**: SQLite with schema in `database/schema.sql`

## Build/Lint/Test Commands

### Development Server

```bash
# Start development server (auto-reload enabled)
cd app && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or run directly
python3 -m uvicorn app.main:app --reload
```

### Database & Data

```bash
# Initialize database
sqlite3 practice.db < database/schema.sql

# Import data
python3 app/import_data.py

# Validate JSON exam data
jq . tk202601.json > /dev/null && echo "Valid JSON"

# Count questions in exam
jq '.questions | length' tk202601.json
```

### Testing

```bash
# Install test dependencies (already in requirements.txt)
pip install pytest pytest-asyncio httpx

# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py -v

# Run single test
pytest tests/test_api.py::test_get_questions -v

# Run with coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Check Python syntax
python3 -m py_compile app/main.py

# Format code (if black is installed)
black app/ --line-length 100

# Sort imports (if isort is installed)
isort app/
```

## Code Style Guidelines

### Project Structure

```
tk/
├── app/
│   ├── main.py          # FastAPI application & API endpoints
│   └── import_data.py  # Data import scripts
├── database/
│   └── schema.sql      # Database schema
├── tests/              # Test files (create if needed)
├── tk202601.json       # Exam question data
├── student.xlsx        # Student records
└── requirements.txt   # Python dependencies
```

### Naming Conventions

- **Files**: snake_case (e.g., `main.py`, `import_data.py`)
- **Classes**: PascalCase (e.g., `Student`, `Question`)
- **Functions/variables**: snake_case (e.g., `get_db`, `correct_answer`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DATABASE`, `MAX_SESSION_TIME`)
- **Database tables**: snake_case (e.g., `students`, `questions`)

### Import Guidelines

```python
# Standard library first
import json
import os
from datetime import datetime
from typing import List, Optional

# Third-party libraries
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3

# Local imports
from . import models
```

### Type Hints

Use type hints for all function parameters and return values:

```python
def get_student(student_id: int) -> Optional[dict]:
    ...

def calculate_score(answers: List[dict]) -> float:
    ...
```

### Pydantic Models

Define request/response models for API endpoints:

```python
class Question(BaseModel):
    id: str
    type: str
    question: str
    score: float
    explanation: Optional[str] = None
    image: Optional[str] = None
    options: Optional[List[dict]] = None
```

### Error Handling

Use HTTPException for API errors:

```python
from fastapi import HTTPException

@app.get("/students/{student_id}")
def get_student(student_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return dict(student)
```

### Database Operations

Use context managers and parameterized queries:

```python
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Use parameterized queries to prevent SQL injection
cursor.execute(
    "SELECT * FROM students WHERE exam_number = ?",
    (exam_number,)
)
```

### JSON Exam Data Conventions

When modifying `tk202601.json`:

```json
{
  "id": "choice-1",
  "type": "choice",
  "question": "题目内容（中文）",
  "score": 2.5,
  "explanation": "答案解析",
  "image": "data:image/jpeg;base64,..." | null,
  "options": [
    {"text": "选项A", "image": null}
  ],
  "correctAnswer": 0
}
```

- Use camelCase for JSON properties
- Use zero-based indexing for `correctAnswer`
- Keep images under 500KB
- Use ISO 8601 dates: `"2026-01-22T12:46:11.156Z"`

### API Response Format

```python
from fastapi.responses import JSONResponse

@app.get("/api/questions")
def get_questions():
    return JSONResponse(content={"code": 200, "data": [...], "message": "success"})
```

### Async/Await

The current project uses synchronous SQLite. Keep functions sync unless needed:

```python
# Current (sync)
@app.get("/questions")
def get_questions():
    conn = get_db()
    ...

# If switching to async DB, use async def
@app.get("/questions")
async def get_questions():
    ...
```

### Documentation

- Add docstrings to public functions
- Use Chinese comments for user-facing text
- Document API endpoints with FastAPI's auto-generated docs

## Testing Guidelines

Create tests in `tests/` directory:

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_questions():
    response = client.get("/api/questions")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
```

## Version Control

- Commit message format: `[feat]`, `[fix]`, `[refactor]`, `[data]`
- Example: `[feat] Add student score tracking`
- Never commit sensitive data or credentials

## Cursor/Copilot Rules

No existing Cursor rules or Copilot instructions found in this repository.

## Project-Specific Notes

- **Language**: Chinese for UI and question content
- **Subject**: Information Technology (信息技术)
- **Level**: High School Academic Proficiency Test
- **Total Score**: 100 points (24 choice + 4 fill questions)
- **Images**: Base64 JPEG encoded in JSON
- **CORS**: Enabled for all origins during development
