# Mio3 Symmetry

A Blender add-on for mesh symmetrization with multiresolution data preserved.（JP/EN）

メッシュ・シェイプキー・頂点グループ・UV・法線・マルチレゾを対称化する Blender アドオンです。

通常マルチレゾとミラーモディファイアは併用しにくいため、対称性を保ちながらモデリングするために作成しました。
その他、メッシュの対称化に関する機能が含まれています。

![](https://raw.githubusercontent.com/mio3io/resources/Mio3QuickSymm/mio3symmetry_multires_20240629.png)

対称側のメッシュの有無や形状を問わず使用できます。

**このアドオンはミラーモディファイアを適用するアドオンではありませんが概ね似たような結果になります。**
ミラー適用後にもメッシュを編集したり左右対称にしたいというケースに使用できます。

## ダウンロード

https://addon.mio3io.com/

「Self-Hosted Extensions」のダウンロードからドラッグ＆ドロップしてインストールできます

## 互換性

Blender Ver 4.2 以降

## 機能

- メッシュを対称化（マルチレゾの状態を維持する）
- シェイプキーを対称化
- サフィックスがつく頂点グループを対称化（\_L/\_Rなど）

### オプション

- カスタムノーマル
- UV マップ
- サフィックスがつくシェイプキーを非対称化（\_L/\_Rなどを片側用表情に修正）

### <s>UV マップのグループ化（廃止）</s>

![](https://raw.githubusercontent.com/mio3io/resources/Mio3QuickSymm/mio3symmetry_groups_20240629.png)

<s>グループを作成することでパーツ別に U 座標・オフセットを指定できます。</s>

ジオメトリノードベースでの実装に移行したため、アドオンベースのグループ化機能は廃止しました。

## 場所

### 対称化

3D View > Menu > Object

# Info

対称側のメッシュの存在に関わらず要素のインデックスは新しく生成されます。

ミラー適用や対称化と同様に中心の同じ位置にある頂点はマージされます。
上下の唇など結合したくない頂点を重ねないようにしてください。

# ToDo

UDIM 対応
