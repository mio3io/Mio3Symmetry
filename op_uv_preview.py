import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader

mio3qs_preview_msgbus = object()


def callback(cls, context):
    MIO3QS_OT_UvPreview.handle_remove()
    bpy.msgbus.clear_by_owner(mio3qs_preview_msgbus)


def reload_view(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.tag_redraw()


class MIO3QS_OT_UvPreviewRefresh(bpy.types.Operator):
    bl_idname = "mio3qs.preview_refresh"
    bl_label = "Refresh Mesh"
    bl_description = "Refresh Mesh"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None and context.active_object.mode == "EDIT"
        )
    def execute(self, context):
        MIO3QS_OT_UvPreview.update_mesh(context)
        reload_view(context)
        return {"FINISHED"}


class MIO3QS_OT_UvPreview(bpy.types.Operator):
    bl_idname = "mio3qs.preview"
    bl_label = "Preview UV"
    bl_description = "Preview UV"
    bl_options = {"REGISTER", "UNDO"}

    __handle = None
    __shader = None
    __region = None
    __color = (0.5, 0.5, 0.5, 1)
    __vertices = []

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None and context.active_object.mode == "EDIT"
        )

    def execute(self, context):
        context.scene.tool_settings.use_uv_select_sync = False
        if not MIO3QS_OT_UvPreview.is_running():
            self.handle_add(context)
        else:
            MIO3QS_OT_UvPreview.handle_remove()
        reload_view(context)
        return {"FINISHED"}

    @classmethod
    def __draw(cls, context):
        # cls.update_mesh(context)
        viewport_vertices = [
            cls.__region.view2d.view_to_region(v[0], v[1], clip=False) for v in cls.__vertices
        ]
        batch = batch_for_shader(cls.__shader, "LINES", {"pos": viewport_vertices})

        cls.__shader.bind()
        cls.__shader.uniform_float("color", cls.__color)
        batch.draw(cls.__shader)

    @classmethod
    def is_running(cls):
        return cls.__handle is not None

    @classmethod
    def handle_add(cls, context):
        cls.__handle = bpy.types.SpaceImageEditor.draw_handler_add(
            cls.__draw, (context,), "WINDOW", "POST_PIXEL"
        )
        cls.__shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        cls.update_mesh(context)

        bpy.msgbus.subscribe_rna(
            key=(bpy.types.Object, "mode"),
            owner=mio3qs_preview_msgbus,
            args=(cls, context),
            notify=callback,
        )
        area = next(a for a in context.screen.areas if a.type == "IMAGE_EDITOR")
        cls.__region = next(r for r in area.regions if r.type == "WINDOW")

    @classmethod
    def redraw(cls, context):
        if cls.is_running():
            cls.update_mesh(context)
            reload_view(context)

    @classmethod
    def update_mesh(cls, context):
        cls.__vertices = []
        if cls.is_running():
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.active
            deform_layer = bm.verts.layers.deform.active

            def mirror_uv(uv, u_co, offset_v):
                mirrored_uv = uv.copy()
                if abs(mirrored_uv.x - u_co) < 0.0001:
                    mirrored_uv.x = u_co
                mirrored_uv.x = u_co + (u_co - mirrored_uv.x)
                if offset_v:
                    mirrored_uv.y += offset_v
                return mirrored_uv

            face_groups = {}
            processed_faces = set()

            for item in obj.mio3qs.vglist.items:
                vg = obj.vertex_groups.get(item.vertex_group)
                if vg:
                    face_groups[item.vertex_group] = set()
                    for f in bm.faces:
                        if f not in processed_faces:
                            try:
                                if all(vg.index in v[deform_layer] for v in f.verts):
                                    face_groups[item.vertex_group].add(f)
                                    processed_faces.add(f)
                            except:
                                pass

            for face in bm.faces:
                poly_uvs = [loop[uv_layer].uv.copy() for loop in face.loops]
                if face in processed_faces:
                    for item in obj.mio3qs.vglist.items:
                        if face in face_groups.get(item.vertex_group, set()):
                            poly_uvs = [
                                mirror_uv(uv, item.uv_coord_u, item.uv_offset_v)
                                for uv in poly_uvs
                            ]
                            break
                else:
                    poly_uvs = [mirror_uv(uv, 0.5, 0) for uv in poly_uvs]
                
                for i in range(len(poly_uvs)):
                    cls.__vertices.extend([poly_uvs[i], poly_uvs[(i + 1) % len(poly_uvs)]])

            bm.free()

    @classmethod
    def handle_remove(cls):
        if cls.is_running():
            bpy.types.SpaceImageEditor.draw_handler_remove(cls.__handle, "WINDOW")
            cls.__handle = None
            cls.__shader = None
            cls.__region= None
            cls.__vertices = []
            bpy.msgbus.clear_by_owner(mio3qs_preview_msgbus)

    @classmethod
    def unregister(cls):
        cls.handle_remove()


@bpy.app.handlers.persistent
def load_handler(dummy):
    MIO3QS_OT_UvPreview.handle_remove()


classes = [MIO3QS_OT_UvPreview, MIO3QS_OT_UvPreviewRefresh]


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.app.handlers.load_post.append(load_handler)


def unregister():
    bpy.app.handlers.load_post.remove(load_handler)
    for c in classes:
        bpy.utils.unregister_class(c)
