# -*- coding: utf-8 -*-
"""生成播放器目录里的「检查是否完整.bat」。

为什么用脚本生成而不是手写文件：
  .bat 里的中文必须是 GBK（代码页 936），用编辑器存成 UTF-8 会在
  cmd 窗口里变乱码。这个脚本负责保证编码和 CRLF 永远正确。

为什么需要这个 bat：
  PyInstaller 打出来的 _internal\\base_library.zip 是压缩的 Python 字节码，
  360安全卫士 / 卡巴斯基 经常把它当病毒删掉。删了以后双击 exe 只会弹一句
  「Failed to start embedded python interpreter」，玩家完全不知道发生了什么。
"""

import io
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(r"C:\Users\hafeizhou\Desktop\饥荒留声机播放器\检查是否完整.bat")

# (相对路径, 中文说明)
CHECKS = [
    ("DSTMusicPlayer.exe", "主程序"),
    ("_internal\\base_library.zip", "Python 核心库"),
    ("_internal\\python38.dll", "Python 运行库"),
    ("_internal\\_tkinter.pyd", "窗口模块"),
    ("_internal\\tcl86t.dll", "Tcl 库"),
    ("_internal\\tk86t.dll", "Tk 库"),
    ("_internal\\_tcl_data\\init.tcl", "Tcl 数据"),
    ("_internal\\_tk_data\\tk.tcl", "Tk 数据"),
    ("_internal\\_sounddevice_data\\portaudio-binaries\\libportaudio64bit.dll", "声音输出库"),
]

# 完整包的文件总数，低于这个数就说明解压不完整
MIN_FILES = 1000


def build():
    lines = []
    add = lines.append

    add("@echo off")
    add("setlocal enabledelayedexpansion")
    add("title 饥荒留声机播放器 - 文件完整性检查")
    add('set "HERE=%~dp0"')
    add('set "MISS=0"')
    add('set "MISSLIST="')
    add("")
    add("echo.")
    add("echo ==================================================")
    add("echo    饥荒留声机播放器 - 文件完整性检查")
    add("echo ==================================================")
    add("echo.")

    for path, desc in CHECKS:
        add('if exist "%%HERE%%%s" (' % path)
        add("  echo   [OK]   %s" % desc)
        add(") else (")
        add("  echo   [缺失] %s    ^<== %s" % (desc, path))
        add("  set /a MISS+=1")
        add('  set "MISSLIST=!MISSLIST! %s"' % desc)
        add(")")
        add("")

    add('for /f %%c in (\'dir /s /b /a-d "%%HERE%%*" 2^>nul ^| find /c /v ""\') do set COUNT=%%c')
    add("echo.")
    add("echo   文件总数：!COUNT!  （完整版应该是 %d 个以上）" % MIN_FILES)
    add("echo.")
    add("echo --------------------------------------------------")
    add("if !MISS! equ 0 (")
    add("  if !COUNT! lss %d (" % MIN_FILES)
    add("    echo   [警告] 文件数量偏少，可能没解压完整。")
    add("    echo          请重新解压整个压缩包。")
    add("  ) else (")
    add("    echo   检查结果：全部正常，可以直接用了。")
    add("    echo   双击 DSTMusicPlayer.exe 就能打开。")
    add("  )")
    add(") else (")
    add("  echo   检查结果：发现 !MISS! 个问题！")
    add('  echo   缺少的文件：!MISSLIST!')
    add("  echo.")
    add("  echo   最常见的原因：360安全卫士 / 卡巴斯基 把它当病毒删了。")
    add("  echo   这类文件是 Python 的打包库，不是病毒，但安全软件经常误删。")
    add("  echo.")
    add("  echo   怎么解决（按顺序做）：")
    add("  echo     1. 打开 360安全卫士 或 卡巴斯基")
    add("  echo     2. 找到「隔离区 / 恢复区 / 病毒查杀记录」")
    add("  echo     3. 如果看到 DSTMusicPlayer 相关文件，选「恢复」")
    add("  echo        找不到也没关系，直接做下一步")
    add("  echo     4. 把这个「饥荒留声机播放器」文件夹加入白名单 / 信任区")
    add("  echo        - 360：木马查杀 - 信任区 - 添加目录")
    add("  echo        - 卡巴斯基：设置 - 安全 - 威胁与排除 - 管理排除项")
    add("  echo     5. 重新解压压缩包，覆盖到当前文件夹")
    add("  echo     6. 再双击本程序检查一次，看到「全部正常」就行了")
    add("  echo.")
    add("  echo   还不行就发邮件：3024026103@qq.com")
    add("  echo   主题写：1846275+播放器打不开+当前日期")
    add(")")
    add("echo --------------------------------------------------")
    add("echo.")
    add("echo   按任意键关闭...")
    add("pause >nul")
    add("endlocal")

    return "\r\n".join(lines) + "\r\n"


def main():
    if not OUT.parent.is_dir():
        print("目录不存在：%s" % OUT.parent)
        return 1

    text = build()
    with io.open(OUT, "w", encoding="gbk", newline="") as f:
        f.write(text)

    print("已生成：%s" % OUT)
    print("  大小：%d 字节，%d 行，GBK + CRLF" % (OUT.stat().st_size, len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
