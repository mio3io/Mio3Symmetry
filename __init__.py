import bpy
from bpy.types import Operator, Panel
from bpy.props import EnumProperty, BoolProperty
from bpy.app.translations import pgettext
from . import op_symmetrize
from . import op_uv_group
from . import op_uv_preview

bl_info = {
    "name": "Mio3 Symmetry",
    "author": "mio",
    "version": (0, 9, 2),
    "blender": (3, 6, 0),
    "location": "View3D > Object",
    "description": "Symmetrize meshes, shape keys, vertex groups, UVs, and normals while maintaining multi-resolution",
    "category": "Object",
}


translation_dict = {
    "ja_JP": {
        ("*", "Mio3 Symmetry"): "対称化＆リカバリー",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"): "メッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
        ("*", "UnSymmetrize L/R Facial ShapeKeys"): "L/Rの表情シェイプキーを非対称化",
        ("*", "Remove Mirror Modifier"): "ミラーモディファイアを削除",
        ("*", "Origin to Center"): "原点を基準に対称化",
        ("*", "Object is not a mesh"): "オブジェクトがメッシュではありません",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals while maintaining multi-resolution"): "マルチレゾを維持してメッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
        ("*", "Align to vertex position"): "頂点位置に合わせる",
        ("*", "Align to cursor position"): "カーソル位置に合わせる",
        ("*", "Add group Align to vertex or cursor position"): "グループを追加 頂点またはカーソル位置に合わせる",
    }  # fmt: skip
}


modules = [
    op_symmetrize,
    op_uv_group,
    op_uv_preview,
]


def register():
    bpy.app.translations.register(__name__, translation_dict)
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
    bpy.app.translations.unregister(__name__)


if __name__ == "__main__":
    register()
