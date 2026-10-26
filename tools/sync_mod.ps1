# 把桌面工程里的 mod 文件同步到「游戏真正读取」的 mods 目录
# 注意：DST 读的是游戏安装目录下的 mods，不是文档里的那个
# 改完 modmain.lua / modinfo.lua 之后，右键运行这个脚本，然后重启游戏

$src = Split-Path -Parent $PSScriptRoot
$dst = "D:\SteamLibrary\steamapps\common\Don't Starve Together\mods\myfirstmod"

if (-not (Test-Path (Split-Path $dst -Parent))) {
    Write-Host "找不到游戏 mods 目录：$dst"
    Write-Host "请确认游戏装在哪，改一下这个脚本里的路径。"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dst | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dst "scripts\prefabs") | Out-Null

Copy-Item (Join-Path $src "modinfo.lua") $dst -Force
Copy-Item (Join-Path $src "modmain.lua") $dst -Force
Copy-Item (Join-Path $src "scripts\prefabs\pcbridge_record.lua") (Join-Path $dst "scripts\prefabs") -Force

foreach ($extra in @("modicon.tex", "modicon.xml", "说明书.txt")) {
    $file = Join-Path $src $extra
    if (Test-Path $file) {
        Copy-Item $file $dst -Force
    }
}

Write-Host "已同步到：$dst"
Get-ChildItem $dst -Recurse -File | ForEach-Object { Write-Host ("  " + $_.Name) }
Write-Host ""
Write-Host "重启游戏后，Mods 菜单里就能看到「更好的唱片（可连电脑）」和它的图标了。"
