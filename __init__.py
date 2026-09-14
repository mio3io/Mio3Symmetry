import bpy
from . import op_symmetrize
from . import op_normal_symmetrize


translation_dict = {
    "ja_JP": {
        ("Operator", "Symmetrize & Recovery"): "対称化＆リカバリー",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"): "メッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
        ("*", "Asymmetrize L/R Facial ShapeKeys"): "L/Rの表情シェイプキーを非対称化",
        ("*", "Object is not a mesh"): "オブジェクトがメッシュではありません",
    }  # fmt: skip
}


modules = [
    op_symmetrize,
    op_normal_symmetrize,
]


def register():
    for module in modules:
        module.register()

    bpy.app.translations.register(__name__, translation_dict)


def unregister():
    bpy.app.translations.unregister(__name__)

    for module in reversed(modules):
        module.unregister()
