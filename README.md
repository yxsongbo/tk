# 📝 信息技术学业水平考试练习系统

支持100人同时在线练习，实时分析学生答题情况。

## 📊 系统架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   学生端     │────▶│  FastAPI    │────▶│   SQLite    │
│  (index.html)│     │   后端服务   │     │   数据库    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   教师端     │
                    │(teacher.html)│
                    └─────────────┘
```

## 🎯 核心功能

### 1. 学生端
- ✅ 选择班级和学生身份
- ✅ 在线答题（选择题）
- ✅ 实时显示答题解析
- ✅ 自动计分
- ✅ 答题进度跟踪

### 2. 教师分析面板
- ✅ **题目分析**：查看每道题的答题情况
  - 哪些学生答了这道题
  - 每个学生选择的答案
  - 答题正确率统计
  - 选项分布可视化
  - 答题用时分析
  
- ✅ **学生分析**：查看每个学生的答题情况
  - 答题总数
  - 正确率
  - 得分统计
  - 每道题的答题详情
  
- ✅ **题目概览**：所有题目的正确率排行
  - 识别难题（正确率低）
  - 识别易题（正确率高）

## 🛠️ 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 后端 | FastAPI + Python | 高性能异步Web框架 |
| 数据库 | SQLite | 轻量级，支持100并发 |
| 前端 | HTML + CSS + JavaScript | 纯前端，无需构建 |
| 数据 | Pandas | Excel数据导入 |

## 📦 安装部署

### 1. 安装依赖

```bash
# 安装Python依赖
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
# 创建数据库并导入数据
python app/import_data.py
```

这将：
- 从 `student.xlsx` 导入692名学生
- 从 `tk202601.json` 导入28道题目

### 3. 启动服务

```bash
# 启动后端服务
python app/main.py
```

服务将在 http://localhost:8000 启动

### 4. 访问系统

- **学生端**：http://localhost:8000/app/index.html
- **教师分析面板**：http://localhost:8000/app/teacher.html
- **API文档**：http://localhost:8000/docs

## 📁 项目结构

```
/Volumes/T7/tk/
├── app/
│   ├── main.py           # FastAPI后端服务
│   ├── import_data.py    # 数据导入脚本
│   ├── index.html        # 学生端界面
│   └── teacher.html      # 教师分析面板
├── database/
│   └── schema.sql        # 数据库结构
├── student.xlsx          # 学生数据
├── tk202601.json         # 题目数据
├── practice.db           # SQLite数据库（自动生成）
└── requirements.txt      # Python依赖
```

## 🔍 核心API接口

### 题目分析（查看一道题哪些学生答了）

```http
GET /api/analysis/question/{question_id}
```

**响应示例**：
```json
{
  "question": {
    "id": "choice-1",
    "content": "右图是某厂家灭火器参数表...",
    "correct_answer": 3
  },
  "statistics": {
    "total_attempts": 85,
    "correct_count": 62,
    "wrong_count": 23,
    "correct_rate": 72.94,
    "option_distribution": {"0": 5, "1": 8, "2": 10, "3": 62}
  },
  "answers": [
    {
      "name": "张三",
      "class_number": 1,
      "student_number": 5,
      "answer": 3,
      "is_correct": true,
      "score": 2.5,
      "answer_time": 45,
      "created_at": "2026-01-26T10:30:00"
    }
  ]
}
```

### 学生分析

```http
GET /api/analysis/student/{student_id}
```

### 总体概览

```http
GET /api/analysis/overview
```

## 🎓 使用流程

### 学生使用流程

1. 打开学生端页面
2. 选择班级
3. 选择自己的姓名
4. 点击"开始练习"
5. 逐题答题并提交
6. 查看解析和得分

### 教师使用流程

1. 打开教师分析面板
2. 在"题目分析"选项卡选择题目
3. 查看：
   - 答题人数统计
   - 正确率
   - 选项分布图
   - 每个学生的答题详情
4. 可筛选班级和答题结果

## 💡 数据库设计亮点

### 为什么选择SQLite？

- ✅ **零配置**：无需安装数据库服务器
- ✅ **轻量级**：单个文件存储所有数据
- ✅ **高并发**：支持100+并发读取
- ✅ **易备份**：直接复制.db文件即可
- ✅ **跨平台**：Windows/Mac/Linux通用

### 核心表结构

```sql
-- 学生答题记录（核心表）
CREATE TABLE answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,      -- 练习会话ID
    student_id INTEGER,      -- 学生ID
    question_id TEXT,        -- 题目ID
    answer TEXT,             -- 学生答案
    is_correct BOOLEAN,      -- 是否正确
    score REAL,              -- 得分
    answer_time INTEGER,     -- 答题用时（秒）
    created_at TIMESTAMP     -- 答题时间
);
```

## 📈 性能优化

- 添加了关键字段索引，确保查询速度
- 支持100人同时在线无压力
- 每30秒自动刷新数据

## 🔒 安全说明

- 当前为演示版本，未添加身份验证
- 生产环境建议添加教师登录验证
- 学生答题数据实时保存，防止丢失

## 📝 更新日志

### v1.0.0 (2026-01-26)
- ✅ 基础练习功能
- ✅ 题目分析功能
- ✅ 学生分析功能
- ✅ 实时统计面板

## 🤝 技术支持

如有问题，请联系技术支持。

---

**Made with ❤️ for Education**
