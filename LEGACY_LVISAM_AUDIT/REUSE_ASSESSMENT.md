# REUSE ASSESSMENT

前提として、旧スクリプトの**ソースコードは1本も受け取っていません**。以下は文書に書かれた挙動だけに基づく判定です。コードを見れば判定が変わる可能性があります。

## REUSE AS-IS（そのまま使う：考え方・手順）

| 対象 | 出典 | 理由 |
|---|---|---|
| 発散判定＝軌跡範囲の物理妥当性（reset 0、NaN/Inf 0、SIGABRT/SIGSEGV 0、静止時の重力 +Z≈9.8） | S §5, K §6.4, G p20 | 環境に依存しない物理判定。旧資料で「綺麗に見えたが発散していた」実例がある |
| 「着色が走った」を成功とみなさない原則 | S, G ch9 | 現行 Gate 設計と一致 |
| 出力先をタイムスタンプ付きで不変にする（上書き・削除を廃止） | A §2-1, L | データ消失事故の予防 |
| PointCloud2 は構造化配列で読む（`read_points_numpy` を使わない） | M §10.4(1) | Ouster の混在型フィールドで実際に例外が出た |
| 「実機で確認するまで凍結」「導出値は権威ではない」 | G ch9 | 現行 QA 思想と一致 |

## REUSE WITH ADAPTATION（調整して使う）

| 対象 | 出典 | 使える部分 | 置き換えが必要な部分 |
|---|---|---|---|
| 投影規約 `p_cam = R·p_lidar + t`（行優先 R、カメラ光学座標 X右/Y下/Z前） | M §9 | 規約と標準軸の導出 | **source frame を実際の PointCloud2 の frame_id（os_lidar か os_sensor か）で明記**。RPY は使わず行列（＋四元数）で保存 |
| `cv2.projectPoints` による歪み込み投影 | M §10.1 | 歪みを含めて投影する方針 | 現行の検証済み K/D、境界マージン、z-buffer を追加 |
| 平面ベース外部較正のワークフロー（capture → plane forensic → multi-hypothesis solve → visual check → 着色側だけに適用） | G p35 | 段階構成と「SLAM 本体には入れない」規則 | 手持ち → 三脚固定、定性 → 定量 holdout、ボード寸法の実測。run23/24 のコードは未確認 |
| 既知色物体による定性 QA（彩度分布、赤の収束） | K §7, G p23 | 補助的 QA | 主判定は定量（NEXT_PLAN F/J） |
| ROS camera_calibration による対話撮影 | M §8 | 撮影時のライブ coverage 表示 | 合否判定には使わない。検出器・ソルバは現行 campaign framework を維持 |

## REFERENCE ONLY（参照のみ）

| 対象 | 出典 | 理由 |
|---|---|---|
| bag 記録時刻を橋渡しにした最近傍画像選択（time_bridge.csv） | G p23, O §2.1 | 経緯の参考。転送遅延を含み補間もないため production には不適 |
| LVI-SAM の外部パラメータ3系統の整理 | K §5, G ch5 | 概念整理としては有用。現行は LIO-SAM なので camera→IMU は使わない |
| object detection v6（XYZ アンカー） | O | 着色後の用途例。較正とは無関係 |
| LiDAR–IMU 外部パラメータが2系統あった件（identity と diag(-1,-1,1)） | M, G p17 | frame_id 混同の教訓。値は使わない |

## DO NOT REUSE（使わない）

| 対象 | 出典 | 理由 |
|---|---|---|
| 旧 K/D（640×360 と 1280×720 の両方） | G p6, p14, p28 | 解像度・クロップ・カメラが異なる。検証も学習誤差のみ |
| 旧 extrinsic（tz=0.065 の手測り値、v24 の R/t） | K §5.4, G p32 | マウント変更済み、frame 規約に疑義、定量検証なし |
| LiDAR–IMU extrinsic、IMU ノイズ、mappingCornerLeafSize 等の OS0-32 用値 | M, G, F | センサーもドライバも異なる。Gate B は既に現行値で PASS |
| `require_time_sync=false`（最新画像へのフォールバック） | M §10.3 | 時刻不一致を黙って受け入れてしまう |
| 視野外を灰色で埋める（grey fallback） | M §10.1, G p23 | 未着色と着色済みが区別できず、エラーも隠れる |
| voxel 蓄積・上書きによる着色 | M §10.1 | 幾何と点順序を変えてしまう |
| colored_map.pcd の writer（`x y z rgb` のみ） | M §15.3 | intensity/ring/t 等を落とし、点数・順序も変わる |
| リアルタイム着色ノード構成 | M §2, S | 色付き構成のときだけ発散した実績がある |
