import bpy
from bpy.types import Operator, Panel
from bpy.props import EnumProperty, BoolProperty
from bpy.app.translations import pgettext
import bmesh

import time

bl_info = {
    "name": "Mio3 Quick Symmetry",
    "author": "mio",
    "version": (0, 9, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Object",
    "description": "Symmetrize meshes, shape keys, vertex groups, UVs, and normals while maintaining multi-resolution",
    "category": "Object",
}

TempVGName = "Mio3qsTempVg"
TempDataTransferName = "Mio3qsTempDataTransfer"


class MIO3_OT_quick_symmetrize(Operator):
    bl_idname = "object.mio3_quick_symmetry"
    bl_label = "Quick Symmetry"
    bl_description = "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Mode",
        default="+X",
        items=[
            ("+X", "+X → -X", ""),
            ("-X", "-X → +X", ""),
        ],
    )
    normal: BoolProperty(name="Normal", default=True)
    uvmap: BoolProperty(name="UVMap", default=True)
    center: BoolProperty(name="Origin to Center", default=True)
    remove_mirror_mod: BoolProperty(name="Remove Mirror Modifier", default=True)

    threshold = 0.0001
    suffixes = [
        ("_r", ".r", "-r", " r", "right", "_R", ".R", "-R", " R", "Right"),
        ("_l", ".l", "-l", " l", "left", "_L", ".L", "-L", " L", "Left"),
    ]

    main_verts = []
    sub_verts = []
    original_cursor_location = None
    original_active_shape_key_index = None

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None and context.active_object.mode == "OBJECT"
        )

    def invoke(self, context, event):
        obj = context.active_object
        if obj.type != "MESH":
            self.report({"ERROR"}, "Object is not a mesh")
            return {"CANCELLED"}

        # bpy.ops.ed.undo_push()  # mesh.symmetrizeがReDoできない措置

        self.original_cursor_location = tuple(bpy.context.scene.cursor.location)
        self.original_active_shape_key_index = obj.active_shape_key_index
        self.original_location = obj.location

        return self.execute(context)

    def execute(self, context):
        start_time = time.time()
        self.obj = context.active_object
        obj = self.obj

        for o in bpy.context.scene.objects:
            if o != obj:
                o.select_set(False)

        # 状態を保存
        if self.center and obj.location.x != 0:
            bpy.context.scene.cursor.location = (0,) + self.original_location[1:]
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

        bpy.ops.object.mode_set(mode="EDIT")

        for mod in self.obj.modifiers:
            if self.remove_mirror_mod and mod.type == "MIRROR":
                obj.modifiers.remove(mod)

        vart_count_1 = len(self.obj.data.vertices)

        orig_shapekey_weights = []
        if self.obj.data.shape_keys:
            for key in self.obj.data.shape_keys.key_blocks:
                orig_shapekey_weights.append(key.value)
                key.value = 0
            self.obj.active_shape_key_index = 0

        orig_modifier_states = []
        for mod in self.obj.modifiers:
            orig_modifier_states.append(mod.show_viewport)
            mod.show_viewport = False

        self.orgcopy = self.obj.copy()
        self.orgcopy.data = self.obj.data.copy()
        bpy.context.collection.objects.link(self.orgcopy)

        # 対称化

        bm = bmesh.from_edit_mesh(self.obj.data)

        bmesh.ops.symmetrize(
            bm,
            input=bm.verts[:] + bm.edges[:] + bm.faces[:],
            direction="X" if self.mode == "+X" else "-X",
            use_shapekey=True,
            dist=0.0001,
        )

        for elem in bm.verts[:] + bm.edges[:] + bm.faces[:]:
            elem.hide_set(False)
            elem.select_set(False)

        select_condition = lambda x: x <= 0 if self.mode == "+X" else x >= 0
        for v in bm.verts:
            if select_condition(v.co.x):
                v.select = True

        if self.uvmap:
            self.symm_uv(bm)
        self.symm_vgroups()

        bmesh.update_edit_mesh(self.obj.data)

        if self.normal:
            self.create_temp_vgroup()
            self.symm_normal()

        # 状態を戻す
        if self.obj.data.shape_keys:
            for i, weight in enumerate(orig_shapekey_weights):
                self.obj.data.shape_keys.key_blocks[i].value = weight
        for i, state in enumerate(orig_modifier_states):
            self.obj.modifiers[i].show_viewport = state

        if self.original_active_shape_key_index is not None:
            self.obj.active_shape_key_index = self.original_active_shape_key_index

        if self.original_cursor_location is not None:
            bpy.context.scene.cursor.location = self.original_cursor_location

        if TempVGName in self.obj.vertex_groups:
            self.obj.vertex_groups.remove(self.obj.vertex_groups[TempVGName])

        bpy.data.objects.remove(self.orgcopy, do_unlink=True)

        if self.obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        vart_count_2 = len(self.obj.data.vertices)
        stime = time.time() - start_time
        self.report({"INFO"}, f"Quick Symmetry Vertex Count {vart_count_1} → {vart_count_2}  Time: {stime:.4f}")  # fmt:skip
        return {"FINISHED"}

    # 頂点グループを作る
    def create_temp_vgroup(self):
        bpy.context.scene.tool_settings.vertex_group_weight = 1
        if TempVGName in self.obj.vertex_groups:
            self.vg = self.obj.vertex_groups[TempVGName]
            self.obj.vertex_groups.active_index = self.vg.index
            bpy.ops.object.vertex_group_remove_from(use_all_verts=True)
        else:
            self.vg = self.obj.vertex_groups.new(name=TempVGName)
            self.obj.vertex_groups.active_index = self.vg.index
        bpy.ops.object.vertex_group_assign()

        return self.vg

    # UV
    def symm_uv(self, bm):
        for v in bm.verts:
            v.select = False
        bm.select_flush(False)

        select_condition = lambda x: x < 0 if self.mode == "+X" else x > 0
        for v in bm.verts:
            if select_condition(v.co.x):
                v.select = True
                for f in v.link_faces:
                    f.select = True

        uv_layer = bm.loops.layers.uv.active

        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer]
                # 中心はマージさせる
                if abs(uv.uv.x - 0.5) < 0.0001:
                    uv.uv.x = 0.5
                if face.select:
                    uv.uv.x = 1 - uv.uv.x

    # 頂点ウェイト
    def symm_vgroups(self):
        vgroups = self.obj.vertex_groups
        suffixes = self.suffixes[0] if self.mode == "+X" else self.suffixes[1]
        suffixes = [
            name for name in vgroups.keys() if name.endswith(suffixes, True)
        ]
        for suffix in suffixes:
            from_group = vgroups.get(suffix)
            if from_group:
                self.obj.vertex_groups.active_index = from_group.index
                bpy.ops.object.vertex_group_mirror(use_topology=False)

    # 法線
    def symm_normal(self):
        bpy.ops.object.mode_set(mode="OBJECT")

        self.orgcopy.scale[0] *= -1
        try:
            transfer_modifier = self.obj.modifiers.new(
                name=TempDataTransferName, type="DATA_TRANSFER"
            )
            transfer_modifier.object = self.orgcopy
            transfer_modifier.vertex_group = self.vg.name
            transfer_modifier.data_types_loops = {"CUSTOM_NORMAL"}
            bpy.context.view_layer.objects.active = self.obj
            bpy.ops.object.modifier_apply(modifier=transfer_modifier.name)
        finally:
            self.orgcopy.scale[0] *= -1
            pass

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode")
        layout.prop(self, "normal")
        layout.prop(self, "uvmap")
        layout.prop(self, "center")
        layout.prop(self, "remove_mirror_mod")


def menu_transform(self, context):
    self.layout.separator()
    self.layout.operator(
        MIO3_OT_quick_symmetrize.bl_idname,
        text=pgettext(MIO3_OT_quick_symmetrize.bl_label),
    )


translation_dict = {
    "ja_JP": {
        ("*", "Quick Symmetry"): "対称化＆リカバリー",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"): "メッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
        ("*", "Remove Mirror Modifier"): "ミラーモディファイアを削除",
        ("*", "Origin to Center"): "原点を基準に対称化",
        ("*", "Object is not a mesh"): "オブジェクトがメッシュではありません",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals while maintaining multi-resolution"): "マルチレゾを維持してメッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
    }  # fmt: skip
}


classes = [MIO3_OT_quick_symmetrize]


def register():
    bpy.types.VIEW3D_MT_object.append(menu_transform)
    bpy.app.translations.register(__name__, translation_dict)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.app.translations.unregister(__name__)
    bpy.types.VIEW3D_MT_object.remove(menu_transform)


if __name__ == "__main__":
    register()
