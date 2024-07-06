import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty
from bpy.app.translations import pgettext
import bmesh
import time

TMP_VG_NAME = "Mio3qsTempVg"
TMP_DATA_TRANSFER_NAME = "Mio3qsTempDataTransfer"


class MIO3_OT_quick_symmetrize(Operator):
    bl_idname = "object.mio3_symmetry"
    bl_label = "Mio3 Symmetry"
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
    facial: BoolProperty(name="UnSymmetrize L/R Facial ShapeKeys", default=False)
    normal: BoolProperty(name="Normal", default=True)
    uvmap: BoolProperty(name="UVMap", default=True)
    center: BoolProperty(name="Origin to Center", default=True)
    remove_mirror_mod: BoolProperty(name="Remove Mirror Modifier", default=True)

    suffixes = [
        ("_r", ".r", "-r", " r", "_R", ".R", "-R", " R", "Right"),
        ("_l", ".l", "-l", " l", "_L", ".L", "-L", " L", "Left"),
    ]

    main_verts = []
    sub_verts = []
    original_cursor_location = None
    original_active_shape_key_index = None

    replace_names = {
        "ウィンク": "MMD_Wink_R",
        "ウィンク右": "MMD_Wink_L",
        "ウィンク２": "MMD_Wink2_R",
        "ｳｨﾝｸ２右": "MMD_Wink2_L",
    }

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
        self.original_active_vertex_groups_index = obj.vertex_groups.active_index

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
            dist=0.00001,
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

        if self.facial:
            self.unsymm_facial()

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

        if self.original_active_vertex_groups_index is not None:
            obj.vertex_groups.active_index = self.original_active_vertex_groups_index

        if self.original_cursor_location is not None:
            bpy.context.scene.cursor.location = self.original_cursor_location

        if TMP_VG_NAME in self.obj.vertex_groups:
            self.obj.vertex_groups.remove(self.obj.vertex_groups[TMP_VG_NAME])

        bpy.data.objects.remove(self.orgcopy, do_unlink=True)

        if self.obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        vart_count_2 = len(self.obj.data.vertices)
        stime = time.time() - start_time
        self.report({"INFO"}, f"Mio3 Symmetry Vertex Count {vart_count_1} → {vart_count_2}  Time: {stime:.4f}")  # fmt:skip
        return {"FINISHED"}

    # 頂点グループを作る
    def create_temp_vgroup(self):
        bpy.context.scene.tool_settings.vertex_group_weight = 1
        if TMP_VG_NAME in self.obj.vertex_groups:
            self.vg = self.obj.vertex_groups[TMP_VG_NAME]
            self.obj.vertex_groups.active_index = self.vg.index
            bpy.ops.object.vertex_group_remove_from(use_all_verts=True)
        else:
            self.vg = self.obj.vertex_groups.new(name=TMP_VG_NAME)
            self.obj.vertex_groups.active_index = self.vg.index
        bpy.ops.object.vertex_group_assign()

        return self.vg

    # UV
    def symm_uv(self, bm):
        obj = self.obj
        deform_layer = bm.verts.layers.deform.active
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            return

        def mirror_uv(faces, u_co, offset_v):
            for face in faces:
                for loop in face.loops:
                    uv = loop[uv_layer]
                    if abs(uv.uv.x - u_co) < 0.0001:
                        uv.uv.x = u_co
                    uv.uv.x = u_co + (u_co - uv.uv.x)
                    if offset_v:
                        uv.uv.y = uv.uv.y + offset_v

        face_groups = {}
        processed_faces = set()
        select_condition = lambda x: x < 0 if self.mode == "+X" else x > 0
        for item in obj.mio3qs.vglist.items:
            vg = obj.vertex_groups.get(item.vertex_group)
            if vg:
                face_groups[item.vertex_group] = set()
                for f in bm.faces:
                    if f not in processed_faces:
                        # グループに登録されている
                        try:
                            if all(vg.index in v[deform_layer] for v in f.verts):
                                # 片側の面
                                if any(select_condition(v.co.x) for v in f.verts):
                                    face_groups[item.vertex_group].add(f)
                                processed_faces.add(f)
                        except:
                            pass

        # グループごとに処理
        for item in obj.mio3qs.vglist.items:
            if item.vertex_group in face_groups:
                mirror_uv(face_groups[item.vertex_group], item.uv_coord_u, item.uv_offset_v)

        # General
        general_faces = set(bm.faces) - processed_faces
        selected_general_faces = [
            f for f in general_faces if any(select_condition(v.co.x) for v in f.verts)
        ]
        mirror_uv(selected_general_faces, 0.5, 0)

    # 頂点ウェイト
    def symm_vgroups(self):
        vgroups = self.obj.vertex_groups
        suffixes = self.suffixes[0] if self.mode == "+X" else self.suffixes[1]
        suffixes = [name for name in vgroups.keys() if name.endswith(suffixes, True)]
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
                name=TMP_DATA_TRANSFER_NAME, type="DATA_TRANSFER"
            )
            transfer_modifier.object = self.orgcopy
            transfer_modifier.vertex_group = self.vg.name
            transfer_modifier.data_types_loops = {"CUSTOM_NORMAL"}
            bpy.context.view_layer.objects.active = self.obj
            bpy.ops.object.modifier_apply(modifier=transfer_modifier.name)
        finally:
            self.orgcopy.scale[0] *= -1
            pass

    # 表情の非対称化
    def unsymm_facial(self):
        obj = self.obj
        original_use_mesh_mirror_x = obj.use_mesh_mirror_x
        obj.use_mesh_mirror_x = False
        if not  obj.data.shape_keys:
            return
        key_blocks = obj.data.shape_keys.key_blocks

        if not obj.data.total_vert_sel:
            return

        if not key_blocks:
            return

        side_suffixes = {
            "+X": (self.suffixes[0], self.suffixes[1]),
            "-X": (self.suffixes[1], self.suffixes[0]),
        }
        target_suffixes, source_suffixes = side_suffixes[self.mode]

        basis = key_blocks[0]
        self.rename_shape_keys(obj, self.replace_names)
        try:
            for i, shape_key in enumerate(key_blocks):
                for target_suffix, source_suffix in zip(
                    target_suffixes, source_suffixes
                ):
                    if shape_key.name.endswith(target_suffix):
                        source_name = (
                            shape_key.name[: -len(target_suffix)] + source_suffix
                        )
                        if source_name in key_blocks:
                            obj.active_shape_key_index = i
                            bpy.ops.mesh.blend_from_shape(
                                shape=source_name, blend=1, add=False
                            )
                            obj.active_shape_key_index = key_blocks.find(source_name)
                            bpy.ops.mesh.blend_from_shape(
                                shape=basis.name, blend=1, add=False
                            )
                            break
            obj.active_shape_key_index = 0
        finally:
            reverse_names = {v: k for k, v in self.replace_names.items()}
            self.rename_shape_keys(obj, reverse_names)
            obj.use_mesh_mirror_x = original_use_mesh_mirror_x

    def rename_shape_keys(self, obj, dicts):
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                if key.name in dicts:
                    key.name = dicts[key.name]

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode")
        layout.prop(self, "facial")
        layout.prop(self, "normal")
        layout.prop(self, "uvmap")
        layout.prop(self, "center")
        layout.prop(self, "remove_mirror_mod")


classes = [MIO3_OT_quick_symmetrize]


def menu_transform(self, context):
    self.layout.separator()
    self.layout.operator(
        MIO3_OT_quick_symmetrize.bl_idname,
        text=pgettext(MIO3_OT_quick_symmetrize.bl_label),
    )


def register():
    bpy.types.VIEW3D_MT_object.append(menu_transform)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object.remove(menu_transform)
