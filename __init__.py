import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, StringProperty
from . import op_symmetrize
from . import op_symmetrize_group
from . import op_symmetrize_preview
from . import op_normal_symmetrize
from .utils import check_register, check_unregister


translation_dict = {
    "ja_JP": {
        ("Operator", "Symmetrize & Recovery"): "対称化＆リカバリー",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals"): "メッシュ・シェイプキー・頂点グループ・UV・法線を対称化",
        ("*", "Asymmetrize L/R Facial ShapeKeys"): "L/Rの表情シェイプキーを非対称化",
        ("*", "Object is not a mesh"): "オブジェクトがメッシュではありません",
        ("*", "Symmetrize meshes, shape keys, vertex groups, UVs, and normals while maintaining multi-resolution"): "マルチレゾを維持してメッシュ・シェイプキー・頂点グループ・UV・法線を対称化",

        ("Operator", "Add Group"): "グループを追加",
        ("*", "Create a new UV group"): "新しいUVグループを作成する",
        ("Operator", "Remove Group"): "グループを削除",
        ("*", "Remove an active group"): "アクティブなグループを削除する",
        ("Operator", "Update from 2D Cursor"): "2Dカーソルからグループを更新",
        ("*", "Update Group coords from 2D Cursor"): "2Dカーソルからグループの座標を更新します",
        ("Operator", "Update from UV"): "UVからグループを更新",
        ("*", "Update Group coords from Active UV"): "アクティブなUVからグループの座標を更新します",

        ("Operator", "Un Assign"): "割り当て解除",
        ("Operator", "Preview"): "プレビュー",
    }  # fmt: skip
}


class PREFERENCE_mio3symm(AddonPreferences):
    bl_idname = __package__

    def update_use_uv_group(self, context):
        if self.use_uv_group:
            check_register(op_symmetrize_group.MIO3QS_PT_main)
        else:
            check_unregister(op_symmetrize_group.MIO3QS_PT_main)

    use_uv_group: BoolProperty(
        name="UV Group",
        default=False,
        description="Use UV Group for Symmetrize Preview Operator",
        update=update_use_uv_group,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_decorate = False
        layout.prop(self, "use_uv_group")


modules = [
    op_symmetrize,
    op_symmetrize_preview,
    op_symmetrize_group,
    op_normal_symmetrize,
]


def register():
    bpy.utils.register_class(PREFERENCE_mio3symm)

    for module in modules:
        module.register()

    bpy.app.translations.register(__name__, translation_dict)


def unregister():
    bpy.app.translations.unregister(__name__)

    for module in reversed(modules):
        module.unregister()

    bpy.utils.unregister_class(PREFERENCE_mio3symm)
