@echo off
setlocal
cd /d "%~dp0"
rem ============================================================
rem  VitalsRing 打包脚本（PyInstaller 单目录 + 无控制台）
rem  用法：双击本文件，或在本目录命令行执行 build_exe.bat
rem  产物：dist\VitalsRing\VitalsRing.exe（整个 VitalsRing 目录一起拷走才能运行）
rem  说明：
rem   1. 只调用项目内 .venv，不污染全局环境；
rem   2. 单目录 + 无控制台（--windowed）：双击只出挂件，不弹黑框；
rem   3. --collect-submodules PyQt6 防止漏掉 Qt 平台插件导致启动即崩；
rem   4. PyInstaller 只是打包工具，不写进 requirements.txt。
rem  本文件以 GBK 编码保存，不使用 chcp，避免命令行解析乱码。
rem ============================================================

echo [1/4] 检查虚拟环境 ...
if not exist ".venv\Scripts\python.exe" (
  echo   [错误] 找不到 .venv\Scripts\python.exe
  echo   请先在本目录按 README「手动安装依赖」创建虚拟环境。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import PyInstaller, PyQt6, psutil" >nul 2>&1
if errorlevel 1 (
  echo   [错误] 虚拟环境缺少 PyInstaller / PyQt6 / psutil
  echo   请执行： .venv\Scripts\python.exe -m pip install pyinstaller PyQt6 psutil
  pause
  exit /b 1
)

echo [2/4] 清理旧的 build 与 dist ...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [3/4] 调用 PyInstaller（单目录 + 无控制台，约 1-3 分钟）...
set "UPXOPT="
where upx.exe >nul 2>&1 && for %%U in (upx.exe) do set "UPXOPT=--upx-dir=%%~dp$PATH:U"
if defined UPXOPT (echo   [UPX] 检测到 UPX，启用压缩) else (echo   [UPX] 未安装，跳过压缩)

".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name VitalsRing ^
  --collect-submodules PyQt6 ^
  --exclude-module tkinter ^
  --exclude-module PyQt6.QtNetwork ^
  --exclude-module PyQt6.QtQml ^
  --exclude-module PyQt6.QtQuick ^
  --exclude-module PyQt6.QtQuickWidgets ^
  --exclude-module PyQt6.QtWebEngineCore ^
  --exclude-module PyQt6.QtWebEngineWidgets ^
  --exclude-module PyQt6.QtWebChannel ^
  --exclude-module PyQt6.QtMultimedia ^
  --exclude-module PyQt6.QtSql ^
  --exclude-module PyQt6.QtTest ^
  --exclude-module PyQt6.QtDesigner ^
  --exclude-module PyQt6.QtPdf ^
  --exclude-module PyQt6.QtCharts ^
  --exclude-module PyQt6.QtDataVisualization ^
  --exclude-module PyQt6.QtBluetooth ^
  --exclude-module PyQt6.QtNfc ^
  --exclude-module PyQt6.QtPositioning ^
  --exclude-module PyQt6.QtSerialPort ^
  --exclude-module PyQt6.QtSensors ^
  --exclude-module PyQt6.QtWebSockets ^
  --exclude-module PyQt6.QtDBus ^
  %UPXOPT% ^
  main.py
if errorlevel 1 goto failed

echo [4/4] 完成。
echo   产物： %~dp0dist\VitalsRing\VitalsRing.exe
echo   提示： vitalsring_config.json 会生成在 exe 同目录（dist\VitalsRing\），
echo          不会写进 _internal。整个 dist\VitalsRing 目录请一起复制。
exit /b 0

:failed
echo.
echo   [失败] PyInstaller 返回非零退出码，请把上面的报错整段复制出来。
pause
exit /b 1
