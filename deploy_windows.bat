@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "PYTHON_CMD="
set "FIRST_INIT=0"
set "HOST=0.0.0.0"
set "PORT=8000"

if not exist "practice.db" set "FIRST_INIT=1"

where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [错误] 未检测到 Python 3，请先安装 Python 3.10+ 并勾选 Add Python to PATH。
    pause
    exit /b 1
)

echo [1/7] 检查 Python...
%PYTHON_CMD% --version || goto :error

if not exist ".venv" (
    echo [2/7] 创建虚拟环境 .venv ...
    %PYTHON_CMD% -m venv .venv || goto :error
) else (
    echo [2/7] 虚拟环境已存在，跳过创建。
)

call ".venv\Scripts\activate.bat" || goto :error

echo [3/7] 升级 pip...
python -m pip install --upgrade pip || goto :error

echo [4/7] 安装依赖...
python -m pip install -r requirements.txt || goto :error

if not exist "exams" mkdir exams

echo [5/7] 初始化数据库结构与试卷配置...
python -c "from app.main import init_db; init_db()" || goto :error

if "%FIRST_INIT%"=="1" (
    if exist "student.xlsx" (
        echo [5/7] 首次部署，导入学生数据...
        python -c "from app.import_data import import_students; import_students()" || goto :error
    ) else (
        echo [警告] 未找到 student.xlsx，已跳过学生导入。
    )
) else (
    echo [5/7] 已存在 practice.db，跳过学生重导入。
)

echo [6/7] 配置防火墙 8000 端口（失败可忽略）...
netsh advfirewall firewall show rule name="TK_Practice_8000" >nul 2>&1
if %errorlevel% neq 0 (
    netsh advfirewall firewall add rule name="TK_Practice_8000" dir=in action=allow protocol=TCP localport=%PORT% >nul 2>&1
)

set "LOCAL_IP=127.0.0.1"
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /R /C:"IPv4 Address" /C:"IPv4 地址"') do (
    set "TMP_IP=%%i"
    set "TMP_IP=!TMP_IP: =!"
    if not "!TMP_IP!"=="" (
        set "LOCAL_IP=!TMP_IP!"
        goto :ip_ok
    )
)
:ip_ok

echo [7/7] 启动服务...
echo.
echo 学生端： http://%LOCAL_IP%:%PORT%/xx
echo 教师端： http://%LOCAL_IP%:%PORT%/xx/js
echo.
echo 提示：窗口保持打开即服务运行。按 Ctrl+C 可停止服务。
echo.

python -m uvicorn app.main:app --host %HOST% --port %PORT%
exit /b 0

:error
echo.
echo [失败] 部署过程中出现错误，请根据上方日志排查。
pause
exit /b 1
