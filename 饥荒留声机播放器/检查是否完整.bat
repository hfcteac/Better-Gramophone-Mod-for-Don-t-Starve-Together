@echo off
setlocal enabledelayedexpansion
title 饥荒留声机播放器 - 文件完整性检查
set "HERE=%~dp0"
set "MISS=0"
set "MISSLIST="

echo.
echo ==================================================
echo    饥荒留声机播放器 - 文件完整性检查
echo ==================================================
echo.
if exist "%HERE%DSTMusicPlayer.exe" (
  echo   [OK]   主程序
) else (
  echo   [缺失] 主程序    ^<== DSTMusicPlayer.exe
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! 主程序"
)

if exist "%HERE%_internal\base_library.zip" (
  echo   [OK]   Python 核心库
) else (
  echo   [缺失] Python 核心库    ^<== _internal\base_library.zip
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! Python 核心库"
)

if exist "%HERE%_internal\python38.dll" (
  echo   [OK]   Python 运行库
) else (
  echo   [缺失] Python 运行库    ^<== _internal\python38.dll
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! Python 运行库"
)

if exist "%HERE%_internal\_tkinter.pyd" (
  echo   [OK]   窗口模块
) else (
  echo   [缺失] 窗口模块    ^<== _internal\_tkinter.pyd
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! 窗口模块"
)

if exist "%HERE%_internal\tcl86t.dll" (
  echo   [OK]   Tcl 库
) else (
  echo   [缺失] Tcl 库    ^<== _internal\tcl86t.dll
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! Tcl 库"
)

if exist "%HERE%_internal\tk86t.dll" (
  echo   [OK]   Tk 库
) else (
  echo   [缺失] Tk 库    ^<== _internal\tk86t.dll
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! Tk 库"
)

if exist "%HERE%_internal\_tcl_data\init.tcl" (
  echo   [OK]   Tcl 数据
) else (
  echo   [缺失] Tcl 数据    ^<== _internal\_tcl_data\init.tcl
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! Tcl 数据"
)

if exist "%HERE%_internal\_tk_data\tk.tcl" (
  echo   [OK]   Tk 数据
) else (
  echo   [缺失] Tk 数据    ^<== _internal\_tk_data\tk.tcl
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! Tk 数据"
)

if exist "%HERE%_internal\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll" (
  echo   [OK]   声音输出库
) else (
  echo   [缺失] 声音输出库    ^<== _internal\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll
  set /a MISS+=1
  set "MISSLIST=!MISSLIST! 声音输出库"
)

for /f %%c in ('dir /s /b /a-d "%%HERE%%*" 2^>nul ^| find /c /v ""') do set COUNT=%%c
echo.
echo   文件总数：!COUNT!  （完整版应该是 1000 个以上）
echo.
echo --------------------------------------------------
if !MISS! equ 0 (
  if !COUNT! lss 1000 (
    echo   [警告] 文件数量偏少，可能没解压完整。
    echo          请重新解压整个压缩包。
  ) else (
    echo   检查结果：全部正常，可以直接用了。
    echo   双击 DSTMusicPlayer.exe 就能打开。
  )
) else (
  echo   检查结果：发现 !MISS! 个问题！
  echo   缺少的文件：!MISSLIST!
  echo.
  echo   最常见的原因：360安全卫士 / 卡巴斯基 把它当病毒删了。
  echo   这类文件是 Python 的打包库，不是病毒，但安全软件经常误删。
  echo.
  echo   怎么解决（按顺序做）：
  echo     1. 打开 360安全卫士 或 卡巴斯基
  echo     2. 找到「隔离区 / 恢复区 / 病毒查杀记录」
  echo     3. 如果看到 DSTMusicPlayer 相关文件，选「恢复」
  echo        找不到也没关系，直接做下一步
  echo     4. 把这个「饥荒留声机播放器」文件夹加入白名单 / 信任区
  echo        - 360：木马查杀 - 信任区 - 添加目录
  echo        - 卡巴斯基：设置 - 安全 - 威胁与排除 - 管理排除项
  echo     5. 重新解压压缩包，覆盖到当前文件夹
  echo     6. 再双击本程序检查一次，看到「全部正常」就行了
  echo.
  echo   还不行就发邮件：3024026103@qq.com
  echo   主题写：1846275+播放器打不开+当前日期
)
echo --------------------------------------------------
echo.
echo   按任意键关闭...
pause >nul
endlocal
