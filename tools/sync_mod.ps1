# 把仓库里的 mod 文件同步到「游戏真正读取」的 mods 目录
# 注意：DST 读的是游戏安装目录下的 mods，不是文档里的那个
# 改完 modmain.lua / modinfo.lua 之后，运行这个脚本，然后重启游戏
#
# 路径全部自动推算：
#   $src  = 本脚本上一级（仓库根）
#   $dst  = 游戏安装目录\mods\myfirstmod（自动探测）
# 想手动指定游戏位置就先设环境变量：
#   $env:DST_DIR = "D:\SteamLibrary\steamapps\common\Don't Starve Together"

$src = Split-Path -Parent $PSScriptRoot

function Find-GameDir {
    if ($env:DST_DIR) {
        if (Test-Path (Join-Path $env:DST_DIR "bin64")) {
            return $env:DST_DIR
        }
    }

    $bases = @(
        "\SteamLibrary\steamapps\common",
        "\Program Files (x86)\Steam\steamapps\common",
        "\Program Files\Steam\steamapps\common",
        "\Games\Steam\steamapps\common",
        "\Steam\steamapps\common"
    )

    foreach ($drive in @("C:", "D:", "E:", "F:", "G:")) {
        foreach ($base in $bases) {
            $candidate = Join-Path ($drive + $base) "Don't Starve Together"
            if (Test-Path (Join-Path $candidate "bin64")) {
                return $candidate
            }
        }
    }
    return $null
}

$game = Find-GameDir
if (-not $game) {
    Write-Host "找不到饥荒安装目录。"
    Write-Host ""
    Write-Host "请先用环境变量指定游戏位置，再运行本脚本："
    Write-Host '    $env:DST_DIR = "D:\SteamLibrary\steamapps\common\Don''t Starve Together"'
    exit 1
}

$dst = Join-Path $game "mods\myfirstmod"

Write-Host "源目录  : $src"
Write-Host "目标目录: $dst"
Write-Host ""

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
