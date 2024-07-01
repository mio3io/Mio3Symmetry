# Mio3 Symmetry

メッシュ・シェイプキー・頂点グループ・UV・法線・マルチレゾを対称化する Blender アドオンです（JP/EN）

通常マルチレゾとミラーモディファイアは併用しにくいため、このアドオンを使用すると対称性を保ちながらモデリングすることができます。

![](https://raw.githubusercontent.com/mio3io/resources/Mio3QuickSymm/mio3symmetry_multires_20240629.png)

このアドオンはミラーモディファイアを適用するアドオンではありませんが概ね似たような結果になります。
ミラー適用後にもメッシュを編集したり左右対称にしたいというケースにも使用できます。

## 導入方法

[Code > Download ZIP](https://github.com/mio3io/Mio3Symmetry/archive/master.zip) から ZIP ファイルをダウンロードします。
Blender の `Edit > Preferences > Addons > Install` を開き、ダウンロードしたアドオンの ZIP ファイルを選択してインストールボタンを押します。インストール後、該当するアドオンの左側についているチェックボックスを ON にします。

## 機能

-   メッシュを対称化（マルチレゾの状態を維持する）
-   シェイプキーを対称化
-   頂点グループを対称化

### オプション

-   カスタムノーマル
-   UV マップ
-   _L/_R のついている表情シェイプキーを非対称にする

### UV マップのグループ化

![](https://raw.githubusercontent.com/mio3io/resources/Mio3QuickSymm/mio3symmetry_groups_20240629.png)

UV マップのミラーリングは通常は中心座標 0.5 で対称化しますが、頂点グループを登録することでパーツ別に U 座標・オフセットを指定できます。

対称のメッシュがあってもなくても使用できます。このアドオンはミラーモディファイアに依存しないため、事前に設定したり適用する必要はありません。（通常設定ではミラーモディファイアがあれば自動的に削除されます）

## 場所

オブジェクトのメニューに「対称化＆リカバリー」が追加されます

# Info

ミラー適用や対称化と同様に中心の同じ位置にある頂点はマージされます。上下の唇など結合したくない頂点を重ねないようにしてください。中心の頂点が近すぎると頂点の数が増加することがあります。

# ToDo

UDIM 対応