name = "更好的唱片（可连电脑）"
description = [[
给留声机加一张「连接电脑」的唱片。
放进留声机响了才出声，离得越远声音越小，关闭立刻安静。
使用前先在电脑上打开「饥荒留声机播放器」。
配方：一根树枝（工具页），不需要科学机器。
【注意】
· 需电脑本地音乐文件，暂不支持网易云、QQ音乐、酷狗等在线播放。
· 播放器平时也可以当作普通音乐播放器使用，不开游戏也能听。
· 播放器下载：哔哩哔哩：
　GitHub：github.com/hfcteac/Better-Gramophone-Mod-for-Don-t-Starve-Together
【兼容】留声机照常给作物唱歌促生长，30多个插件同开不报错不闪退。
【BUG 反馈】邮箱 3024026103@qq.com
主题：1846275+Bug反馈+当前时间（年月日）
正文写清 bug，作者会尽快处理。
【更新】1.2.0 加距离｜1.2.3 左右平衡｜1.2.4 修洞穴掉线
（照片是我对象，他已经离开了。我再也没有找到过他，好想他。）
]]

author = "hafeizhou"
version = "1.2.4"

api_version = 10
dst_compatible = true
dont_starve_compatible = false
reign_of_giants_compatible = false
all_clients_require_mod = false
client_only_mod = false
server_filter_tags = {}

icon_atlas = "modicon.xml"
icon = "modicon.tex"

configuration_options =
{
    {
        name = "VOLUME",
        label = "总音量",
        hover = "唱片的最大音量，实际音量还会随距离衰减",
        options =
        {
            { description = "20%", data = 0.2 },
            { description = "40%", data = 0.4 },
            { description = "60%", data = 0.6 },
            { description = "80%", data = 0.8 },
            { description = "100%", data = 1.0 },
        },
        default = 1.0,
    },
    {
        name = "CARRY_PLAY",
        label = "拿起也能放",
        hover = "把留声机拿在手上、放进背包时，音乐继续播放",
        options =
        {
            { description = "开", data = true },
            { description = "关", data = false },
        },
        default = true,
    },
}
