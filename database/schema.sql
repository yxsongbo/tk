-- 练习系统数据库设计
-- 支持100人同时在线练习

-- 1. 学生表
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_number TEXT UNIQUE NOT NULL,  -- 准考证号
    class_number INTEGER NOT NULL,      -- 班级
    student_number INTEGER NOT NULL,    -- 学号
    name TEXT NOT NULL,                 -- 姓名
    subject_group INTEGER NOT NULL,     -- 组合
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 题目表（从JSON导入）
CREATE TABLE questions (
    id TEXT PRIMARY KEY,                -- 题目ID (如 choice-1)
    type TEXT NOT NULL CHECK(type IN ('choice', 'fill')),  -- 题目类型
    question TEXT NOT NULL,             -- 题目内容
    score REAL NOT NULL,                -- 分值
    explanation TEXT,                   -- 答案解析
    image TEXT,                         -- 图片Base64
    correct_answer INTEGER,             -- 正确答案索引（选择题）
    options TEXT,                       -- 选项JSON数组（选择题）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 练习会话表
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    total_score REAL DEFAULT 0,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'abandoned')),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

-- 4. 答题记录表（核心表）
CREATE TABLE answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    answer TEXT,                        -- 学生答案
    is_correct BOOLEAN,                 -- 是否正确
    score REAL DEFAULT 0,               -- 得分
    answer_time INTEGER,                -- 答题用时（秒）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (question_id) REFERENCES questions(id),
    UNIQUE(session_id, question_id)     -- 每道题每个会话只记录一次
);

-- 5. 索引优化（提高查询性能）
CREATE INDEX idx_answers_question ON answers(question_id);
CREATE INDEX idx_answers_student ON answers(student_id);
CREATE INDEX idx_answers_session ON answers(session_id);
CREATE INDEX idx_answers_created ON answers(created_at);
CREATE INDEX idx_students_exam ON students(exam_number);

-- 查询示例：某道题所有学生的答题情况
-- SELECT 
--     s.name,
--     s.class_number,
--     a.answer,
--     a.is_correct,
--     a.score,
--     a.answer_time,
--     a.created_at
-- FROM answers a
-- JOIN students s ON a.student_id = s.id
-- WHERE a.question_id = 'choice-1'
-- ORDER BY a.created_at DESC;

-- 查询示例：统计每道题的正确率
-- SELECT 
--     q.id,
--     q.question,
--     COUNT(*) as total_attempts,
--     SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) as correct_count,
--     ROUND(100.0 * SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as correct_rate
-- FROM questions q
-- LEFT JOIN answers a ON q.id = a.question_id
-- GROUP BY q.id;

-- 6. 系统设置表
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
