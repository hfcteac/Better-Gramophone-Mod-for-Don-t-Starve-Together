-- 复用游戏自带的唱片美术，不需要额外贴图
local assets =
{
    Asset("ANIM", "anim/records.zip"),
    Asset("INV_IMAGE", "record"),
}

local function fn()
    local inst = CreateEntity()

    inst.entity:AddTransform()
    inst.entity:AddAnimState()
    inst.entity:AddNetwork()

    MakeInventoryPhysics(inst)

    inst.AnimState:SetBank("records")
    inst.AnimState:SetBuild("records")
    inst.AnimState:PlayAnimation("idle")

    inst:AddTag("cattoy")
    inst:AddTag("phonograph_record")
    inst:AddTag("pcbridge_record")

    MakeInventoryFloatable(inst, "med", 0.02, 0.7)

    inst.entity:SetPristine()

    if not TheWorld.ismastersim then
        return inst
    end

    inst.scrapbook_tex = "record"

    local inventoryitem = inst:AddComponent("inventoryitem")
    -- 不指定的话图标名默认是 prefab 名（pcbridge_record），图集里没有 → 物品栏里看不见
    inventoryitem:ChangeImageName("record")

    inst:AddComponent("inspectable")
    inst:AddComponent("tradable")

    MakeHauntableLaunchAndIgnite(inst)

    return inst
end

return Prefab("pcbridge_record", fn, assets)
