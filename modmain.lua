-- 让 modmain 能直接用游戏里的全局变量（Ingredient、TECH、STRINGS、TheSim、os ...）
GLOBAL.setmetatable(env, { __index = function(t, k) return GLOBAL.rawget(GLOBAL, k) end })

PrefabFiles = { "pcbridge_record" }

local RECORD_PREFAB = "pcbridge_record"
local RECORD_TAG = "pcbridge_record"
local BRIDGE_KEY = "dst_music_bridge"
local ALIVE_KEY = "dst_music_alive"

local HEARTBEAT_PERIOD = 0.5   -- 每 0.5 秒更新一次，音量跟着玩家位置走
local FULL_VOLUME_RANGE = 12   -- 12 格以内满音量
local SILENT_RANGE = 60        -- 60 格以外完全听不到（1.2.0 从 20 拉大到 60）
local VOLUME = GetModConfigData("VOLUME") or 1
-- 留声机被拿在手上时是否继续播放
local CARRY_PLAY = GetModConfigData("CARRY_PLAY")
if CARRY_PLAY == nil then
    CARRY_PLAY = true
end

STRINGS.NAMES.PCBRIDGE_RECORD = "连接电脑"
STRINGS.RECIPE_DESC.PCBRIDGE_RECORD = "放进留声机，让电脑上的音乐跟着留声机走。"
STRINGS.CHARACTERS.GENERIC.DESCRIBE.PCBRIDGE_RECORD = "这张唱片没有声音，声音在另一个世界。"

-- 一根树枝就能做，谁都能试
AddRecipe2(RECORD_PREFAB,
    { Ingredient("twigs", 1) },
    TECH.NONE,
    { image = "record.tex" },
    { "TOOLS" })

-- 这一整个 mod 的原则：任何一步出错都只是"没声音"，绝不能把游戏带崩
local function Safe(fn, label)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then
            print("[pcbridge] " .. label .. " 出错（已忽略）：" .. tostring(err))
        end
    end
end

-- 找出离留声机最近的玩家，算出音量（只看距离，左右声道固定居中）
local function GetListenerVolume(inst)
    -- 拿在手上时位置会被归零（RemoveFromScene 后 Transform 变成局部坐标），
    -- 所以直接用「贴着耳朵」处理：满音量。
    local inventoryitem = inst.components and inst.components.inventoryitem
    if inventoryitem ~= nil and inventoryitem.owner ~= nil then
        return VOLUME
    end

    local x, _, z = inst.Transform:GetWorldPosition()
    local nearest_distance = nil

    -- 用游戏自己维护的 AllPlayers 全表，比 FindEntities 扫 60 格半径快得多
    local candidates = AllPlayers
    if candidates == nil then
        candidates = TheSim:FindEntities(x, 0, z, SILENT_RANGE, { "player" })
    end

    for _, player in ipairs(candidates) do
        if player:IsValid() and not player:HasTag("playerghost") then
            local px, _, pz = player.Transform:GetWorldPosition()
            local ex, ez = x - px, z - pz
            local distance = math.sqrt(ex * ex + ez * ez)
            if nearest_distance == nil or distance < nearest_distance then
                nearest_distance = distance
            end
        end
    end

    if nearest_distance == nil or nearest_distance >= SILENT_RANGE then
        -- 附近没有任何玩家，或者最近的人也在 60 格外：完全静音。
        return 0
    end
    if nearest_distance < 0.05 then
        return VOLUME
    end

    local falloff = 1 - (nearest_distance - FULL_VOLUME_RANGE) / (SILENT_RANGE - FULL_VOLUME_RANGE)
    return VOLUME * math.max(0, math.min(1, falloff))
end

local function WriteState(inst, action)
    local volume = 0
    if action == "play" and inst ~= nil then
        local ok, v = pcall(GetListenerVolume, inst)
        if ok then
            volume = v or 0
        end
    end

    -- 饥荒禁止 mod 用 io.open 写文件，只能写进存档目录。
    -- pan 固定写 0（左右平衡）：1.2.3 起不再做声道偏移，
    -- 但字段保留，播放器那边就不用改。
    TheSim:SetPersistentString(BRIDGE_KEY, table.concat({
        "action=" .. action,
        "volume=" .. string.format("%.3f", volume),
        "pan=0.000",
        "time=" .. tostring(os.time()),
    }, "\n"), false)
end

local function HasBridgeRecord(inst)
    local inventory = inst ~= nil and inst.components ~= nil and inst.components.inventory
    if inventory == nil or inventory.GetItemsWithTag == nil then
        return false
    end

    local ok, items = pcall(inventory.GetItemsWithTag, inventory, RECORD_TAG)
    return ok and items ~= nil and items[1] ~= nil
end

-- [[ 给别的 mod 兜底：容器也要有 SoundEmitter ]]
-- 有些 mod（例如创意工坊的「AV唱片」）在留声机被移除时会直接写：
--     local owner = inst.components.inventoryitem.owner
--     owner.SoundEmitter:KillSound("xxx")
-- 当留声机被放进背包、然后带着背包进洞穴时，owner 是那个背包而不是玩家。
-- 背包没有 SoundEmitter，那些 mod 就会报 attempt to index field 'SoundEmitter'。
-- 更致命的是：这个错抛在引擎的 PushEvent 里面，会把整个服务器进程带崩 ——
-- 玩家看到的现象就是「你已于服务器断开连接」，而且一进洞穴必现。
--
-- 这里在留声机被放进容器的那一刻先给容器补一个空的 SoundEmitter，
-- 让那些 mod 的调用变成无害的空操作。对容器本身没有任何副作用。
local function EnsureSoundEmitter(owner)
    if owner == nil or owner.SoundEmitter ~= nil or owner.entity == nil then
        return
    end
    pcall(function()
        owner.entity:AddSoundEmitter()
    end)
end

local function StopBridge(inst)
    if inst == nil then
        return
    end
    if inst._tend_task ~= nil then
        local tend = inst._tend_task
        inst._tend_task = nil
        pcall(function() tend:Cancel() end)
    end

    if inst._bridge_task == nil then
        return
    end

    local task = inst._bridge_task
    inst._bridge_task = nil
    pcall(function() task:Cancel() end)
    WriteState(inst, "stop")
end

-- [[ 给作物唱歌 ]]
-- 原版留声机放歌时会每秒给附近的「可照料作物」唱一次歌，让它们生长。
-- 那段逻辑写在原版 TryToPlayRecord 里，被我们接管 turnonfn 后就不会跑了，
-- 所以必须在这里按原版一模一样的做法补上，否则留声机就失去了照料作物的功能。
local FARM_PLANT_TAGS = { "tendable_farmplant" }

local function TendNearbyPlants(inst)
    local range = TUNING ~= nil and TUNING.PHONOGRAPH_TEND_RANGE
    if range == nil then
        return
    end

    -- 拿在手上 / 放进背包时 Transform 会被归零（RemoveFromScene 造成），
    -- 这时算出来的位置是地图原点，绝不能拿它去照料作物。
    local inventoryitem = inst.components ~= nil and inst.components.inventoryitem
    if inventoryitem ~= nil and inventoryitem.owner ~= nil then
        return
    end

    local x, _, z = inst.Transform:GetWorldPosition()

    for _, plant in ipairs(TheSim:FindEntities(x, 0, z, range, FARM_PLANT_TAGS)) do
        local tendable = plant.components ~= nil and plant.components.farmplanttendable
        if tendable ~= nil and tendable.tendable and tendable.ontendtofn ~= nil then
            -- 和原版一样：不带参数调用，让组件自己判断能不能照料
            pcall(tendable.TendTo, tendable)
        end
    end
end

local function StartTending(inst)
    if inst._tend_task ~= nil then
        pcall(function() inst._tend_task:Cancel() end)
        inst._tend_task = nil
    end

    -- 原版是每秒一次，第一次延迟在播种世界时随机，这里照抄
    local initial_delay = POPULATING and math.random() or nil
    inst._tend_task = inst:DoPeriodicTask(1, Safe(function(inst)
        TendNearbyPlants(inst)
    end, "照料作物"), initial_delay)
end

local function StartBridge(inst)
    local machine = inst.components and inst.components.machine
    if machine == nil then
        return
    end

    machine.enabled = true
    if inst.AnimState ~= nil then
        inst.AnimState:PushAnimation("play_loop", true)
    end
    WriteState(inst, "play")

    -- 留声机已经在背包里被开机的情况：容器同样需要兜底
    local carried_by = inst.components.inventoryitem
    if carried_by ~= nil then
        EnsureSoundEmitter(carried_by.owner)
    end

    if inst._bridge_task ~= nil then
        pcall(function() inst._bridge_task:Cancel() end)
        inst._bridge_task = nil
    end

    inst._bridge_task = inst:DoPeriodicTask(HEARTBEAT_PERIOD, Safe(function(inst)
        -- 实体已经被移除时不要再写，免得引用已销毁的对象
        if inst == nil or not inst:IsValid() then
            return
        end

        if not HasBridgeRecord(inst) then
            StopBridge(inst)
            local machine2 = inst.components and inst.components.machine
            if machine2 ~= nil and machine2:IsOn() then
                machine2:TurnOff()
            end
            return
        end

        WriteState(inst, "play")
    end, "心跳"))

    -- 补回原版「给作物唱歌」的效果
    StartTending(inst)
end

-- 告诉电脑端"世界开着了"；进主菜单或者退出游戏就不再写
AddSimPostInit(function()
    local ok = pcall(function()
        if TheWorld == nil or not TheWorld.ismastersim then
            return
        end

        local function beat()
            TheSim:SetPersistentString(ALIVE_KEY, tostring(os.time()), false)
        end

        beat()
        TheWorld:DoPeriodicTask(2, Safe(beat, "心跳"))
    end)
    if not ok then
        print("[pcbridge] 心跳注册失败（已忽略）")
    end
end)

AddPrefabPostInit("phonograph", function(inst)
    if inst == nil or inst.components == nil then
        return inst
    end
    -- 洞穴分片启动时 TheWorld 可能还没建好，这里必须先判空，
    -- 否则 TheWorld.ismastersim 会直接报 nil value
    if TheWorld == nil or not TheWorld.ismastersim then
        return inst
    end

    local machine = inst.components.machine
    if machine == nil then
        return inst
    end

    -- 包一层：只有放的是我们的唱片才接管，其它情况原样交回给游戏（含别的留声机 mod）
    local on_turn_on = machine.turnonfn
    machine.turnonfn = function(inst, ...)
        local ok, handled = pcall(HasBridgeRecord, inst)
        if ok and handled then
            local started = pcall(StartBridge, inst)
            if started then
                return
            end
        end

        if on_turn_on ~= nil then
            pcall(on_turn_on, inst, ...)
        end
    end

    inst:ListenForEvent("turnedoff", Safe(StopBridge, "关闭"))
    inst:ListenForEvent("onremove", Safe(StopBridge, "移除"))

    -- 兜底：万一别的 mod 的 onremove 监听器排在前面，这里再补一次
    inst:ListenForEvent("onremove", Safe(function(inst)
        local inventoryitem = inst.components and inst.components.inventoryitem
        if inventoryitem ~= nil then
            EnsureSoundEmitter(inventoryitem.owner)
        end
    end, "移除兜底"))

    -- 拿起留声机照样播放：原版在被放进背包时会强制关机，这里改成只在
    -- 「放的是我们的唱片」时跳过关机；而且无论如何都先替容器补上 SoundEmitter，
    -- 否则带着背包进洞穴会让别的 mod 崩掉整个服务器。
    local inventoryitem = inst.components.inventoryitem
    if inventoryitem ~= nil then
        local original = inventoryitem.onputininventoryfn

        inventoryitem.onputininventoryfn = function(inst2, owner, ...)
            EnsureSoundEmitter(owner)

            if not CARRY_PLAY then
                if original ~= nil then
                    return original(inst2, owner, ...)
                end
                return
            end

            -- CARRY_PLAY 开着：我们的唱片进背包也继续放，不关机
            if HasBridgeRecord(inst2) then
                return
            end

            if original ~= nil then
                return original(inst2, owner, ...)
            end
        end
    end

    return inst
end)