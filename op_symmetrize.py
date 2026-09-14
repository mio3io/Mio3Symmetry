import bpy
import bmesh
import time
import numpy as np
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty
from .common import NAME_ATTR_GROUP
from .utils_mirror import parse_side_name, get_mirror_name

TMP_VG_NAME = "Mio3qsTempVg"
TMP_DATA_TRANSFER_NAME = "Mio3qsTempDataTransfer"


class OBJECT_OT_mio3_symmetry(Operator):
    bl_idname = "object.mio3_symmetry"
    bl_label = "Symmetrize & Recovery"
    bl_description = "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"
    bl_options = {"REGISTER", "UNDO"}

    orient_type: EnumProperty(name="Orientation", items=[("LOCAL", "Local", ""), ("GLOBAL", "Global", "")])
    direction: EnumProperty(name="Direction", default="+X", items=[("-X", "-X → +X", ""), ("+X", "-X ← +X", "")])
    normal: BoolProperty(name="Normal", default=False)
    uvmap: BoolProperty(name="UVMap", default=False)
    facial: BoolProperty(name="Asymmetrize L/R Facial ShapeKeys", default=False)

    _main_verts = []
    _sub_verts = []
    _replace_name_map = {
        "ウィンク": "MMD_Wink_R",
        "ウィンク右": "MMD_Wink_L",
        "ウィンク２": "MMD_Wink2_R",
        "ｳｨﾝｸ２右": "MMD_Wink2_L",
    }

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.mode == "OBJECT"

    def invoke(self, context, event):
        obj = context.active_object
        if obj.type != "MESH":
            self.report({"ERROR"}, "Object is not a mesh")
            return {"CANCELLED"}

        # bpy.ops.ed.undo_push()  # mesh.symmetrizeがReDoできない措置
        return self.execute(context)

    def execute(self, context):
        start_time = time.time()
        obj = context.active_object

        original_cursor_location = tuple(context.scene.cursor.location)
        original_location = obj.location

        for o in context.scene.objects:
            if o != obj:
                o.select_set(False)

        # 状態を保存
        if self.orient_type == "GLOBAL" and obj.location.x != 0:
            context.scene.cursor.location = (0,) + original_location[1:]
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        active_shape_key_index = obj.active_shape_key_index

        vart_count_1 = len(obj.data.vertices)

        orig_shapekey_weights = []
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                orig_shapekey_weights.append(key.value)
                key.value = 0
            obj.active_shape_key_index = 0

        orig_modifier_states = []
        for mod in obj.modifiers:
            orig_modifier_states.append(mod.show_viewport)
            mod.show_viewport = False

        if self.normal and obj.data.has_custom_normals:
            orgcopy = obj.copy()
            orgcopy.data = obj.data.copy()
            context.collection.objects.link(orgcopy)
        else:
            orgcopy = None

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        # 対称化
        direction = "X" if self.direction == "+X" else "-X"
        data = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.symmetrize(bm, input=data, direction=direction, use_shapekey=True, dist=1e-5)

        for elem in bm.verts[:] + bm.edges[:] + bm.faces[:]:
            elem.hide_set(False)
            elem.select_set(False)

        select_condition = lambda x: x <= 0 if self.direction == "+X" else x >= 0
        for v in bm.verts:
            if select_condition(v.co.x):
                v.select = True

        if self.uvmap:
            self.symm_uv(obj, bm)

        self.symm_vgroups(obj, bm)

        if self.normal and obj.data.has_custom_normals:
            vg = self.create_temp_vgroup(obj, bm)
            vg_name = vg.name  # UnicodeDecodeError 対策
        else:
            vg, vg_name = None, None

        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

        if self.normal and obj.data.has_custom_normals and vg:
            self.symm_normal(obj, orgcopy, vg.name)

        if self.facial:
            self.unsymm_facial(obj)

        # 状態を戻す
        if obj.data.shape_keys:
            for i, weight in enumerate(orig_shapekey_weights):
                obj.data.shape_keys.key_blocks[i].value = weight
        for i, state in enumerate(orig_modifier_states):
            obj.modifiers[i].show_viewport = state

        if original_cursor_location is not None:
            context.scene.cursor.location = original_cursor_location

        obj.active_shape_key_index = active_shape_key_index

        if vg and vg_name in obj.vertex_groups:
            obj.vertex_groups.remove(obj.vertex_groups[vg_name])

        if orgcopy is not None:
            copy_mesh = orgcopy.data
            bpy.data.objects.remove(orgcopy, do_unlink=True)
            bpy.data.meshes.remove(copy_mesh, do_unlink=True)

        vart_count_2 = len(obj.data.vertices)
        stime = time.time() - start_time
        self.report({"INFO"}, f"Mio3 Symmetry {vart_count_1} → {vart_count_2}  Time: {stime:.4f}")  # fmt:skip
        return {"FINISHED"}

    def create_temp_vgroup(self, obj, bm):
        deform_layer = bm.verts.layers.deform.verify()

        if TMP_VG_NAME in obj.vertex_groups:
            vg = obj.vertex_groups[TMP_VG_NAME]
            obj.vertex_groups.remove(vg)
        vg = obj.vertex_groups.new(name=TMP_VG_NAME)

        for v in bm.verts:
            if v.select:
                if v.co.x != 0.0:
                    v[deform_layer][vg.index] = 1.0
        return vg

    # UV
    def symm_uv(self, obj, bm):
        uv_group = obj.mio3qs.uv_group
        uv_layer = bm.loops.layers.uv.active
        p_layer = bm.faces.layers.int.get(NAME_ATTR_GROUP)
        if not uv_layer:
            return

        if self.direction == "+X":
            v_is_source_side = [v.co.x < 0.0 for v in bm.verts]
        else:
            v_is_source_side = [v.co.x > 0.0 for v in bm.verts]

        def face_on_source_side(face) -> bool:
            for v in face.verts:
                if v_is_source_side[v.index]:
                    return True
            return False

        if not p_layer:
            pivot_u = 0.5
            for face in bm.faces:
                if not face_on_source_side(face):
                    continue
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    dx = uv.x - pivot_u
                    uv.x = pivot_u if abs(dx) < 1e-5 else pivot_u - dx
        else:
            coord_u = [it.uv_coord_u for it in uv_group.items]
            offset_v = [it.uv_offset_v for it in uv_group.items]
            u_len = len(coord_u)

            for face in bm.faces:
                if not face_on_source_side(face):
                    continue

                uv_group_idx = face[p_layer]
                if uv_group_idx < 0 or uv_group_idx >= u_len:
                    continue

                pivot_u = coord_u[uv_group_idx]
                off_v = offset_v[uv_group_idx]
                if off_v:
                    for loop in face.loops:
                        uv = loop[uv_layer].uv
                        dx = uv.x - pivot_u
                        uv.x = pivot_u if abs(dx) < 1e-5 else pivot_u - dx
                        uv.y += off_v
                else:
                    for loop in face.loops:
                        uv = loop[uv_layer].uv
                        dx = uv.x - pivot_u
                        uv.x = pivot_u if abs(dx) < 1e-5 else pivot_u - dx

    # 頂点ウェイト
    def symm_vgroups(self, obj, bm):
        deform_layer = bm.verts.layers.deform.verify()
        symmetric_groups = self.symmetric_group_mapping(obj)
        select_condition = lambda x: x <= 0 if self.direction == "+X" else x >= 0

        for v in bm.verts:
            if not (v.select and select_condition(v.co.x)):
                continue

            weight_dict = v[deform_layer]
            if not weight_dict:
                continue

            original = dict(weight_dict)
            weight_dict.clear()
            for vg_id, weight in original.items():
                weight_dict[symmetric_groups.get(vg_id, vg_id)] = weight

    # 法線
    def symm_normal(self, obj, orgcopy, vg_name):
        orgcopy.scale[0] *= -1
        try:
            transfer_modifier = obj.modifiers.new(name=TMP_DATA_TRANSFER_NAME, type="DATA_TRANSFER")
            transfer_modifier.object = orgcopy
            transfer_modifier.vertex_group = vg_name
            transfer_modifier.use_max_distance = True
            transfer_modifier.max_distance = 0.0001
            transfer_modifier.data_types_loops = {"CUSTOM_NORMAL"}
            with bpy.context.temp_override(object=obj):
                bpy.ops.object.modifier_apply(modifier=transfer_modifier.name)

        finally:
            orgcopy.scale[0] *= -1

    # 表情の非対称化
    def unsymm_facial(self, obj):
        if not obj.data.shape_keys:
            return

        key_blocks = obj.data.shape_keys.key_blocks
        if not key_blocks:
            return

        self.rename_shape_keys(obj, self._replace_name_map)

        v_len = len(obj.data.vertices)
        basis = obj.data.shape_keys.reference_key
        basis_coords = np.zeros(v_len * 3, dtype=np.float32)
        basis.data.foreach_get("co", basis_coords)

        target_side_kind = "right" if self.direction == "+X" else "left"

        for i, target_kb in enumerate(key_blocks):
            info = parse_side_name(target_kb.name)
            if not info or not info.get("has_side"):
                continue

            if info["side_kind"] != target_side_kind:
                continue

            source_name = get_mirror_name(target_kb.name)
            if not source_name:
                continue

            source_kb = key_blocks.get(source_name)
            if source_kb is None:
                continue

            vertex_mask = np.array([v.select for v in obj.data.vertices], dtype=bool)
            mask_indices = np.where(vertex_mask)[0]

            if len(mask_indices) == 0:
                continue

            source_coords = np.zeros(v_len * 3, dtype=np.float32)
            source_kb.data.foreach_get("co", source_coords)

            target_coords = np.zeros(v_len * 3, dtype=np.float32)
            target_kb.data.foreach_get("co", target_coords)

            for idx in mask_indices:
                coord_idx = idx * 3
                target_coords[coord_idx : coord_idx + 3] = source_coords[coord_idx : coord_idx + 3]
            target_kb.data.foreach_set("co", target_coords)

            for idx in mask_indices:
                coord_idx = idx * 3
                source_coords[coord_idx : coord_idx + 3] = basis_coords[coord_idx : coord_idx + 3]
            source_kb.data.foreach_set("co", source_coords)

        reverse_name_map = {v: k for k, v in self._replace_name_map.items()}
        self.rename_shape_keys(obj, reverse_name_map)

    def rename_shape_keys(self, obj, map):
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                if key.name in map:
                    key.name = map[key.name]

    def symmetric_group_mapping(self, obj):
        symmetric_groups = {}
        name_to_group = {vg.name: vg for vg in obj.vertex_groups}
        processed_vgroup = set()

        for vgroup in obj.vertex_groups:
            vgroup_name = vgroup.name
            if vgroup_name in processed_vgroup:
                continue

            info = parse_side_name(vgroup_name)
            if not info or not info.get("has_side"):
                symmetric_groups[vgroup.index] = vgroup.index
                processed_vgroup.add(vgroup_name)
                continue

            opposite_name = get_mirror_name(vgroup_name) or vgroup_name
            opposite_group = name_to_group.get(opposite_name) if opposite_name else None

            if not opposite_group or opposite_name == vgroup_name:
                symmetric_groups[vgroup.index] = vgroup.index
                processed_vgroup.add(vgroup_name)
                continue

            symmetric_groups[vgroup.index] = opposite_group.index
            symmetric_groups[opposite_group.index] = vgroup.index
            processed_vgroup.add(vgroup_name)
            processed_vgroup.add(opposite_name)

        return symmetric_groups

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.row().prop(self, "orient_type", expand=True)
        layout.row().prop(self, "direction", expand=True)
        layout.separator()
        layout.use_property_split = False
        box = layout.box()
        col = box.column()
        col.label(text="Options:")
        col.prop(self, "normal")
        col.prop(self, "uvmap")
        col.prop(self, "facial")


classes = [OBJECT_OT_mio3_symmetry]


def menu_transform(self, context):
    self.layout.separator()
    self.layout.operator(OBJECT_OT_mio3_symmetry.bl_idname)


def register():
    bpy.types.VIEW3D_MT_object.append(menu_transform)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object.remove(menu_transform)
