import bpy
from bpy.types import Operator, Panel, UIList, PropertyGroup
from bpy.props import (
    FloatProperty,
    IntProperty,
    StringProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty,
)
import bmesh
from .op_uv_preview import MIO3QS_OT_UvPreview


class MIO3QS_OT_GroupAdd(Operator):
    bl_idname = "mio3qs.group_add"
    bl_label = "Add Item"
    bl_description = "Add group Align to vertex or cursor position"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        items=[
            ("ADD", "Add", ""),
            ("REPLACE", "Replace", "Align to vertex position"),
            ("CURSOR_U", "Cursor", "Align to cursor position"),
            ("CURSOR_V", "Cursor", "Align to cursor position"),
        ],
        options={"HIDDEN"},
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.mode == "EDIT"

    def invoke(self, context, event):

        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "No active mesh object")
            return {"CANCELLED"}

        if self.mode == "ADD":
            selected_group_name = obj.mio3qs.selected_vertex_group
        else:
            vglist = context.object.mio3qs.vglist
            selected_group_name = vglist.items[vglist.active_index].vertex_group

        if not selected_group_name:
            self.report({"ERROR"}, "No vertex group selected")
            return {"CANCELLED"}

        selected_vg = obj.vertex_groups.get(selected_group_name)
        if not selected_vg:
            self.report({"ERROR"}, "Selected vertex group not found")
            return {"CANCELLED"}

        if self.mode in {"ADD", "REPLACE", "CURSOR_V"}:

            # 選択中の頂点のUV座標を取得
            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.verify()
            selected_vert = None
            for face in bm.faces:
                for loop in face.loops:
                    if loop[uv_layer].select:
                        selected_vert = loop[uv_layer].uv
                        break

            if not selected_vert:
                self.report({"ERROR"}, "No vertex selected")
                return {"CANCELLED"}

            new_uv_coord = selected_vert
            vglist = obj.mio3qs.vglist

        # 登録済みかチェック
        update_item = None
        for item in vglist.items:
            if item.vertex_group == selected_group_name:
                update_item = item
                break

        if self.mode == "ADD" and not update_item:
            new_item = vglist.items.add()
            new_item.vertex_group = selected_group_name
            new_item.uv_coord_u = new_uv_coord.x
        elif self.mode == "REPLACE":
            update_item.uv_coord_u = new_uv_coord.x
        elif self.mode == "CURSOR_U":
            update_item.uv_coord_u = context.space_data.cursor_location[0]
        elif self.mode == "CURSOR_V":
            update_item.uv_offset_v = context.space_data.cursor_location[1] - new_uv_coord.y

        return {"FINISHED"}


class MIO3QS_OT_GroupRemove(Operator):
    bl_idname = "mio3qs.group_remove"
    bl_label = "Remove Item"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        vglist = context.object.mio3qs.vglist
        vglist.items.remove(vglist.active_index)
        vglist.active_index = min(max(0, vglist.active_index - 1), len(vglist.items) - 1)
        return {"FINISHED"}


class MIO3QS_OT_GroupMove(Operator):
    bl_idname = "mio3qs.group_move"
    bl_label = "Move Item"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        items=[
            ("UP", "Up", ""),
            ("DOWN", "Down", ""),
        ]
    )

    def execute(self, context):
        obj = context.active_object
        vglist = obj.mio3qs.vglist
        index = vglist.active_index

        if self.direction == "UP" and index > 0:
            vglist.items.move(index, index - 1)
            vglist.active_index -= 1
        elif self.direction == "DOWN" and index < len(vglist.items) - 1:
            vglist.items.move(index, index + 1)
            vglist.active_index += 1

        return {"FINISHED"}


class MIO3QS_PT_SubGroup(Panel):
    bl_label = "Mirror Groups"
    bl_idname = "MIO3QS_PT_SubGroup"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Mio3"
    bl_parent_id = "MIO3QS_PT_Main"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        vglist = obj.mio3qs.vglist

        row = layout.row(align=True)
        row.label(text="Register")
        row.scale_x = 4
        row.prop_search(obj.mio3qs, "selected_vertex_group", obj, "vertex_groups", text="")

        row = layout.row()
        row.template_list(
            "MIO3QS_UL_GroupList",
            "vglist",
            vglist,
            "items",
            vglist,
            "active_index",
            rows=3,
        )

        col = row.column(align=True)
        col.operator("mio3qs.group_add", icon="ADD", text="").mode = "ADD"
        col.operator("mio3qs.group_remove", icon="REMOVE", text="")

        col.separator()
        col.operator("mio3qs.group_move", icon="TRIA_UP", text="").direction = "UP"
        col.operator("mio3qs.group_move", icon="TRIA_DOWN", text="").direction = "DOWN"

        if vglist.items and len(vglist.items) > vglist.active_index:
            item = vglist.items[vglist.active_index]
            row = layout.row(align=True)
            row.prop(item, "uv_coord_u", text="Mirror U")
            row.operator("mio3qs.group_add", icon="UV_VERTEXSEL", text="").mode = "REPLACE"
            row.operator("mio3qs.group_add", icon="PIVOT_CURSOR", text="").mode = "CURSOR_U"
            row = layout.row(align=True)
            row.prop(item, "uv_offset_v", text="Offset V")
            row.operator("mio3qs.group_add", icon="PIVOT_CURSOR", text="").mode = "CURSOR_V"
            row = layout.row(align=True)
            row.prop_search(item, "vertex_group", obj, "vertex_groups", text="")


class MIO3QS_PT_Main(Panel):
    bl_label = "Mio3 QuickSymmetry"
    bl_idname = "MIO3QS_PT_Main"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Mio3"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.mode == "EDIT"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_x = 1.3
        row.operator("mio3qs.preview", text="Preview UV", icon="AREA_SWAP")
        row.operator("mio3qs.preview_refresh", icon="FILE_REFRESH", text="")


class MIO3QS_UL_GroupList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=f"{item.vertex_group}", icon="GROUP_VERTEX")


def update_props(self, context):
    MIO3QS_OT_UvPreview.redraw(context)


class MIO3QS_PG_GroupItem(PropertyGroup):
    vertex_group: StringProperty(name="Vertex Group")
    uv_coord_u: FloatProperty(name="UV U", min=0.0, max=1.0, update=update_props)
    uv_offset_v: FloatProperty(name="Offset V", min=-1.0, max=1.0, update=update_props)


class MIO3QS_PG_GroupList(PropertyGroup):
    items: CollectionProperty(name="items", type=MIO3QS_PG_GroupItem)
    active_index: IntProperty()


class MIO3QS_Props(PropertyGroup):
    vglist: PointerProperty(name="vglist", type=MIO3QS_PG_GroupList)
    selected_vertex_group: StringProperty(name="Selected Vertex Group")


classes = [
    MIO3QS_PG_GroupItem,
    MIO3QS_PG_GroupList,
    MIO3QS_Props,
    MIO3QS_UL_GroupList,
    MIO3QS_OT_GroupAdd,
    MIO3QS_OT_GroupRemove,
    MIO3QS_OT_GroupMove,
    MIO3QS_PT_Main,
    MIO3QS_PT_SubGroup,
]


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.mio3qs = PointerProperty(type=MIO3QS_Props)


def unregister():
    del bpy.types.Object.mio3qs
    for c in classes:
        bpy.utils.unregister_class(c)
