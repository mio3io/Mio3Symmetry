import bpy
from . import op_symmetrize
from . import op_normal_symmetrize


translation_dict = {
    "ja_JP": {
        ("Operator", "Mio3 Symmetrize"): "Mio3 対称化",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"): "メッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
        ("*", "Asymmetrize L/R Facial ShapeKeys"): "L/Rの表情シェイプキーを非対称化",
        ("*", "Object is not a mesh"): "オブジェクトがメッシュではありません",
        ("*", "No faces selected"): "選択された面がありません",
        ("*", "Mirror side region not detected. Select a wider area or faces on both sides"): "ミラー側を検出できませんでした。広めに選択するか、両側の面を選択してください",
        
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
