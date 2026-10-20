@echo off
rem ============================================================
rem  VitalsRing 一键启动脚本（双击本文件即可运行程序）
rem  1. 只用项目内的 .venv 虚拟环境运行 main.py，不污染全局环境；
rem  2. 若 .venv 不存在，自动创建并安装 PyQt6、psutil 依赖；
rem  3. 出错时窗口会停住等待按键，不会一闪而过，方便看清错误。
rem  说明：本文件以 GBK 编码保存，不使用 chcp，避免命令行解析乱码。
rem ============================================================
setlocal
rem 切换到本脚本所在目录，保证双击运行时工作目录正确
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if exist "%VENV_PY%" goto check_deps

rem 没有虚拟环境时，先确认系统里是否装了 Python（创建虚拟环境需要用到）
where python >nul 2>nul
if errorlevel 1 goto no_python
goto create_env

:check_deps
rem 虚拟环境已存在，但可能缺少依赖，做一次轻量校验
"%VENV_PY%" -c "import PyQt6, psutil" >nul 2>nul
if errorlevel 1 goto install_deps
goto run

:create_env
echo 未检测到虚拟环境 .venv，正在创建 ...
python -m venv "%~dp0.venv"
if errorlevel 1 goto fail

:install_deps
echo 正在安装依赖 PyQt6、psutil，首次安装需要联网，请稍候 ...
"%VENV_PY%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto fail
goto run

:run
echo 正在启动 VitalsRing ...
"%VENV_PY%" "%~dp0main.py"
if errorlevel 1 goto fail
echo.
echo VitalsRing 已正常退出，按任意键关闭本窗口。
pause >nul
exit /b 0

:no_python
echo.
echo 没有找到 Python。请先安装 Python 3.10 或更高版本，
echo 安装时务必勾选 Add python.exe to PATH，然后再双击本文件。
echo.
pause >nul
exit /b 1

:fail
echo.
echo 启动失败，请把上面的错误信息截图发给我。
echo.
pause >nul
exit /b 1
