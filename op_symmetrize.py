import bpy
import bmesh
import time
import numpy as np
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty
from mathutils import Matrix, kdtree
from .utils_mirror import parse_side_name, get_mirror_name

TMP_VG_NAME = "Mio3qsTempVg"
TMP_DATA_TRANSFER_NAME = "Mio3qsTempDataTransfer"
TMP_TAG_LAYER = "Mio3qsTempTag"
MERGE_DIST = 1e-5
MIRROR_FIND_DIST = 1e-4


class OBJECT_OT_mio3_symmetry(Operator):
    bl_idname = "object.mio3_symmetry"
    bl_label = "Mio3 Symmetrize"
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
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode in {"OBJECT", "EDIT"}

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

        orig_modifier_states = [mod.show_viewport for mod in obj.modifiers]
        for mod in obj.modifiers:
            mod.show_viewport = False

        def restore_modifiers():
            for mod, state in zip(obj.modifiers, orig_modifier_states):
                mod.show_viewport = state

        mode = obj.mode
        if mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        partial = mode == "EDIT"

        if partial and not any(p.select and not p.hide for p in obj.data.polygons):
            self.report({"WARNING"}, "No faces selected")
            bpy.ops.object.mode_set(mode=mode)
            restore_modifiers()
            return {"CANCELLED"}

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

        if self.normal and obj.data.has_custom_normals:
            orgcopy = obj.copy()
            orgcopy.data = obj.data.copy()
            context.collection.objects.link(orgcopy)
        else:
            orgcopy = None

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        # 層の追加・削除は既存の要素参照を無効化するので、要素を集める前にそろえておく
        bm.verts.layers.deform.verify()
        if partial:
            bm.verts.layers.int.new(TMP_TAG_LAYER)
            bm.faces.layers.int.new(TMP_TAG_LAYER)

        # 対称化
        if partial:
            target_verts, target_faces = self.symmetrize_selected(bm)
            for f in target_faces:
                f.select = True
        else:
            direction = "X" if self.direction == "+X" else "-X"
            data = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.symmetrize(bm, input=data, direction=direction, use_shapekey=True, dist=MERGE_DIST)

            for elem in bm.verts[:] + bm.edges[:] + bm.faces[:]:
                elem.hide_set(False)
                elem.select_set(False)

            select_condition = lambda x: x <= 0 if self.direction == "+X" else x >= 0
            target_verts = [v for v in bm.verts if select_condition(v.co.x)]
            for v in target_verts:
                v.select = True

            new_side = (lambda x: x < 0.0) if self.direction == "+X" else (lambda x: x > 0.0)
            target_faces = [f for f in bm.faces if any(new_side(v.co.x) for v in f.verts)]

        if self.uvmap:
            self.symm_uv(bm, target_faces)

        self.symm_vgroups(obj, bm, target_verts)

        if self.normal and obj.data.has_custom_normals:
            vg = self.create_temp_vgroup(obj, bm, target_verts)
            vg_name = vg.name  # UnicodeDecodeError 対策 ※消すとエラーの可能性
        else:
            vg, vg_name = None, None

        bm.verts.index_update()
        target_mask = np.zeros(len(bm.verts), dtype=bool)
        if target_verts:
            target_mask[[v.index for v in target_verts]] = True

        if partial:
            bm.verts.layers.int.remove(bm.verts.layers.int[TMP_TAG_LAYER])
            bm.faces.layers.int.remove(bm.faces.layers.int[TMP_TAG_LAYER])

        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

        if self.normal and obj.data.has_custom_normals and vg:
            self.symm_normal(obj, orgcopy, vg_name)

        if self.facial:
            self.unsymm_facial(obj, target_mask)

        # 状態を戻す
        if obj.data.shape_keys:
            for i, weight in enumerate(orig_shapekey_weights):
                obj.data.shape_keys.key_blocks[i].value = weight

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
        if not partial or target_faces:
            self.report({"INFO"}, f"Mio3 Symmetry {vart_count_1} → {vart_count_2}  Time: {stime:.4f}")  # fmt:skip
        if mode != "OBJECT":
            bpy.ops.object.mode_set(mode=mode)
        restore_modifiers()
        return {"FINISHED"}

    # 選択した面だけを対称化する
    # bisect → 面単位の削除 → mirror に分解して処理
    def symmetrize_selected(self, bm):
        sign = 1.0 if self.direction == "+X" else -1.0
        tag_v = bm.verts.layers.int[TMP_TAG_LAYER]
        tag_f = bm.faces.layers.int[TMP_TAG_LAYER]

        def is_target(x):
            return x * sign < 0.0

        centers = {f: f.calc_center_median() for f in bm.faces}
        selected = {f for f in bm.faces if f.select and not f.hide}
        source_faces = [f for f in selected if centers[f].x * sign > 0.0]
        target_faces = [f for f in selected if is_target(centers[f].x)]

        if source_faces:
            region = self.find_mirror_region(bm, source_faces, sign, centers)
            if region:
                selected |= region
            elif region is None and not target_faces:
                self.report({"WARNING"}, "Mirror side region not detected. Select a wider area or faces on both sides")
        else:
            region = self.find_mirror_region(bm, target_faces, -sign, centers)
            if not region:
                self.report({"WARNING"}, "Mirror side region not detected. Select a wider area or faces on both sides")
                return [], []
            selected |= region

        selected = list(selected)
        verts = {v for f in selected for v in f.verts}
        edges = {e for f in selected for e in f.edges}
        ret = bmesh.ops.bisect_plane(
            bm,
            geom=list(verts) + list(edges) + selected,
            dist=MERGE_DIST,
            plane_co=(0.0, 0.0, 0.0),
            plane_no=(1.0, 0.0, 0.0),
            use_snap_center=True,
            clear_outer=False,
            clear_inner=False,
        )

        keep_faces = []
        del_faces = []
        for elem in ret["geom"]:
            if isinstance(elem, bmesh.types.BMFace):
                (del_faces if is_target(elem.calc_center_median().x) else keep_faces).append(elem)

        # 面単位で削除する
        if del_faces:
            bmesh.ops.delete(bm, geom=del_faces, context="FACES")

        keep_verts = {v for f in keep_faces for v in f.verts}
        keep_edges = {e for f in keep_faces for e in f.edges}
        for v in keep_verts:
            v[tag_v] = 1
        for f in keep_faces:
            f[tag_f] = 1

        if keep_faces:
            bmesh.ops.mirror(
                bm,
                geom=list(keep_verts) + list(keep_edges) + keep_faces,
                matrix=Matrix.Scale(-1.0, 4, (1.0, 0.0, 0.0)),
                merge_dist=MERGE_DIST,
                axis="X",
                use_shapekey=True,
            )

        # ミラーで作られた頂点を選択境界の既存頂点と溶接する
        new_verts = [v for v in bm.verts if v[tag_v] and is_target(v.co.x)]
        old_verts = [v for v in bm.verts if not v[tag_v] and is_target(v.co.x)]
        if new_verts and old_verts:
            ret = bmesh.ops.find_doubles(bm, verts=new_verts + old_verts, keep_verts=new_verts, dist=MERGE_DIST)
            if ret["targetmap"]:
                bmesh.ops.weld_verts(bm, targetmap=ret["targetmap"])

        new_verts = [v for v in bm.verts if v[tag_v] and is_target(v.co.x)]
        new_faces = [f for f in bm.faces if f[tag_f] and is_target(f.calc_center_median().x)]
        if new_faces:
            bmesh.ops.reverse_faces(bm, faces=new_faces)
        return new_verts, new_faces

    # ソース側の選択境界をミラーし、囲まれた反対側の面を返す
    # 境界の頂点・辺が対称に存在しない場合は None（検出不能）
    def find_mirror_region(self, bm, source_faces, sign, centers):
        if not source_faces:
            return set()
        source_set = set(source_faces)

        def is_target(x):
            return x * sign < 0.0

        def is_target_vert(v):
            return v.co.x * sign < -MERGE_DIST

        kd = kdtree.KDTree(len(bm.verts))
        for i, v in enumerate(bm.verts):
            kd.insert(v.co, i)
        kd.balance()
        bm.verts.ensure_lookup_table()

        mirror_cache = {}

        def mirror_vert(v):
            if v in mirror_cache:
                return mirror_cache[v]
            co = v.co.copy()
            co.x = -co.x
            _, index, dist = kd.find(co)
            m = bm.verts[index] if dist <= MIRROR_FIND_DIST else None
            mirror_cache[v] = m
            return m

        # ミラー辺に接する面のうち、ソース面の中心をミラーした位置と同じ側にある面（＝内側）を返す
        # 反対側の面が分割されていてもミラー辺の内側の面をシードにできる
        def inner_face(me, c_mirror):
            m1, m2 = me.verts
            d = m2.co - m1.co
            d_len_sq = d.length_squared
            if d_len_sq < 1e-12:
                return None
            mid = (m1.co + m2.co) * 0.5
            ref = c_mirror - mid
            ref -= d * (ref.dot(d) / d_len_sq)
            best, best_dot = None, 0.0
            for lf in me.link_faces:
                if lf.hide or not is_target(centers[lf].x):
                    continue
                vec = centers[lf] - mid
                vec -= d * (vec.dot(d) / d_len_sq)
                dot = ref.dot(vec)
                if dot > best_dot:
                    best, best_dot = lf, dot
            return best

        mirror_edges = set()
        seeds = set()
        for f in source_faces:
            c_mirror = None
            for e in f.edges:
                if all(lf in source_set for lf in e.link_faces):
                    continue
                v1, v2 = e.verts
                if abs(v1.co.x) <= MERGE_DIST and abs(v2.co.x) <= MERGE_DIST:
                    continue  # 対称面上の辺
                if is_target_vert(v1) or is_target_vert(v2):
                    continue  # 対称面をまたぐ辺
                m1, m2 = mirror_vert(v1), mirror_vert(v2)
                if m1 is None or m2 is None:
                    return None
                me = bm.edges.get((m1, m2))
                if me is None:
                    return None
                mirror_edges.add(me)

                if c_mirror is None:
                    c_mirror = centers[f].copy()
                    c_mirror.x = -c_mirror.x
                seed = inner_face(me, c_mirror)
                if seed is not None:
                    seeds.add(seed)

        if not seeds:
            return None

        region = set()
        stack = list(seeds)
        while stack:
            f = stack.pop()
            if f in region:
                continue
            region.add(f)
            for e in f.edges:
                if e in mirror_edges:
                    continue
                for lf in e.link_faces:
                    if lf not in region and not lf.hide and is_target(centers[lf].x):
                        stack.append(lf)
        return region

    def create_temp_vgroup(self, obj, bm, target_verts):
        deform_layer = bm.verts.layers.deform.verify()

        if TMP_VG_NAME in obj.vertex_groups:
            vg = obj.vertex_groups[TMP_VG_NAME]
            obj.vertex_groups.remove(vg)
        vg = obj.vertex_groups.new(name=TMP_VG_NAME)

        for v in target_verts:
            if v.co.x != 0.0:
                v[deform_layer][vg.index] = 1.0
        return vg

    # UV
    def symm_uv(self, bm, target_faces):
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            return

        pivot_u = 0.5
        for face in target_faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                dx = uv.x - pivot_u
                uv.x = pivot_u if abs(dx) < 1e-5 else pivot_u - dx

    # 頂点ウェイト
    def symm_vgroups(self, obj, bm, target_verts):
        deform_layer = bm.verts.layers.deform.verify()
        symmetric_groups = self.symmetric_group_mapping(obj)

        for v in target_verts:
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
    def unsymm_facial(self, obj, vertex_mask):
        if not obj.data.shape_keys:
            return

        key_blocks = obj.data.shape_keys.key_blocks
        if not key_blocks:
            return

        mask_indices = np.where(vertex_mask)[0]
        if len(mask_indices) == 0:
            return

        self.rename_shape_keys(obj, self._replace_name_map)

        v_len = len(obj.data.vertices)
        basis = obj.data.shape_keys.reference_key
        basis_coords = np.zeros(v_len * 3, dtype=np.float32)
        basis.data.foreach_get("co", basis_coords)

        target_side_kind = "right" if self.direction == "+X" else "left"

        for target_kb in key_blocks:
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


def menu_mesh(self, context):
    self.layout.separator()
    self.layout.operator(OBJECT_OT_mio3_symmetry.bl_idname)


def register():
    bpy.types.VIEW3D_MT_object.append(menu_transform)
    bpy.types.VIEW3D_MT_edit_mesh.append(menu_mesh)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object.remove(menu_transform)
    bpy.types.VIEW3D_MT_edit_mesh.remove(menu_mesh)
