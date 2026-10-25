-- 让 modmain 能直接用游戏里的全局变量（Ingredient、TECH、STRINGS、TheSim、os ...）
GLOBAL.setmetatable(env, { __index = function(t, k) return GLOBAL.rawget(GLOBAL, k) end })

PrefabFiles = { "pcbridge_record" }

local RECORD_PREFAB = "pcbridge_record"
local RECORD_TAG = "pcbridge_record"
local BRIDGE_KEY = "dst_music_bridge"
local ALIVE_KEY = "dst_music_alive"

local HEARTBEAT_PERIOD = 0.5   -- 每 0.5 秒更新一次，音量和左右声道跟着玩家位置走
local FULL_VOLUME_RANGE = 4    -- 4 格以内满音量
local SILENT_RANGE = 20        -- 20 格以外完全听不到
local VOLUME = GetModConfigData("VOLUME") or 1
-- 左右声道方向。有人听到左右互换，就在 Mods 菜单里改成「反向」。
local PAN_MODE = GetModConfigData("PAN_MODE") or "flip"
local PAN_SIGN = (PAN_MODE == "flip") and -1 or 1
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

-- 找出离留声机最近的玩家，算出音量（距离）和左右声道（屏幕方向）
local function GetListenerSpatial(inst)
    -- 拿在手上时位置会被归零（RemoveFromScene 后 Transform 变成局部坐标），
    -- 所以直接用「贴着耳朵」处理：满音量、不偏声道。
    local inventoryitem = inst.components and inst.components.inventoryitem
    if inventoryitem ~= nil and inventoryitem.owner ~= nil then
        return VOLUME, 0
    end

    local x, _, z = inst.Transform:GetWorldPosition()
    local nearest_distance, dx, dz = nil, 0, 0

    for _, player in ipairs(TheSim:FindEntities(x, 0, z, SILENT_RANGE, { "player" })) do
        if player:IsValid() and not player:HasTag("playerghost") then
            local px, _, pz = player.Transform:GetWorldPosition()
            local ex, ez = x - px, z - pz
            local distance = math.sqrt(ex * ex + ez * ez)
            if nearest_distance == nil or distance < nearest_distance then
                nearest_distance, dx, dz = distance, ex, ez
            end
        end
    end

    if nearest_distance == nil then
        -- 附近没有任何玩家（走出 20 格了）：完全静音。
        -- 这里以前返回 VOLUME，导致走远后突然变响。
        return 0, 0
    end
    if nearest_distance < 0.05 then
        return VOLUME, 0
    end

    local falloff = 1 - (nearest_distance - FULL_VOLUME_RANGE) / (SILENT_RANGE - FULL_VOLUME_RANGE)
    local volume = VOLUME * math.max(0, math.min(1, falloff))

    -- 左右声道：优先用镜头右向量，拿不到就退回 0（单声道）
    local pan = 0
    local ok, right_x, right_z = pcall(function()
        local camera = TheCamera
        if camera ~= nil and camera.GetRightVec ~= nil then
            local right = camera:GetRightVec()
            if right ~= nil then
                return right.x, right.z
            end
        end
        return nil, nil
    end)

    if ok and right_x ~= nil and right_z ~= nil then
        pan = (dx * right_x + dz * right_z) / nearest_distance
    end

    return volume, math.max(-1, math.min(1, pan)) * 0.8 * PAN_SIGN
end

local function WriteState(inst, action)
    local volume, pan = 0, 0
    if action == "play" and inst ~= nil then
        local ok, v, p = pcall(GetListenerSpatial, inst)
        if ok then
            volume, pan = v or 0, p or 0
        end
    end

    -- 饥荒禁止 mod 用 io.open 写文件，只能写进存档目录
    TheSim:SetPersistentString(BRIDGE_KEY, table.concat({
        "action=" .. action,
        "volume=" .. string.format("%.3f", volume),
        "pan=" .. string.format("%.3f", pan),
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

local function StopBridge(inst)
    if inst == nil or inst._bridge_task == nil then
        return
    end

    local task = inst._bridge_task
    inst._bridge_task = nil
    pcall(function() task:Cancel() end)
    WriteState(inst, "stop")
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

    -- 留一行诊断：左右声道还是不对的话，看这行的镜头朝向就知道问题在哪
    pcall(function()
        local heading = "?"
        if TheCamera ~= nil and TheCamera.headingtarget ~= nil then
            heading = string.format("%.1f", TheCamera.headingtarget)
        end
        print(string.format("[pcbridge] 开始播放 镜头朝向=%s 声道方向=%s", heading, PAN_MODE))
    end)

    if inst._bridge_task ~= nil then
        pcall(function() inst._bridge_task:Cancel() end)
        inst._bridge_task = nil
    end

    inst._bridge_task = inst:DoPeriodicTask(HEARTBEAT_PERIOD, Safe(function(inst)
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
    if not TheWorld.ismastersim or inst == nil or inst.components == nil then
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

    -- 拿起留声机照样播放：原版在被放进背包时会强制关机，这里把那个回调去掉
    if CARRY_PLAY then
        local inventoryitem = inst.components.inventoryitem
        if inventoryitem ~= nil then
            local original = inventoryitem.onputininventoryfn
            if original == inst.OnPutInInventory then
                inventoryitem.onputininventoryfn = nil
            elseif original ~= nil then
                -- 别的 mod 也改过这个回调：包一层，只在放的是我们的唱片时跳过
                inventoryitem.onputininventoryfn = function(inst2, owner, ...)
                    if not HasBridgeRecord(inst2) then
                        return original(inst2, owner, ...)
                    end
                end
            end
        end
    end

    return inst
end)