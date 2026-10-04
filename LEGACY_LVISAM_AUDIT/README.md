# LEGACY_LVISAM_AUDIT

旧 LVI-SAM + color map 資産の read-only 監査用ディレクトリ。

## 現状（2026-10-04）

監査対象 `\\CoastalEngLab2\public\個人フォルダ\平野錬磨\LiDAR_開発_LVI SAM+color map\LVI SAM+color map`
は研究室LAN内のWindows共有で、クラウドセッションからは到達できない。
**そのため旧資産の内容に関する CLAIM はまだ1件も存在しない。**
REPORT / EVIDENCE_TABLE / CURRENT_VS_LEGACY / REUSE_ASSESSMENT / NEXT_PLAN は、
収集結果を受け取った後に作成する（未読の資料を推測で埋めないため）。

## Step 1 — 研究室PCで収集（読み取り専用）

共有が見えるPCで（Python 3.8+、標準ライブラリのみ）:

```bat
py tools\collect_legacy_evidence.py ^
  "\\CoastalEngLab2\public\個人フォルダ\平野錬磨\LiDAR_開発_LVI SAM+color map\LVI SAM+color map" ^
  C:\temp\LEGACY_LVISAM_AUDIT_OUT
```

安全性:
- 共有フォルダへは `stat` と読み取りのみ。書き込み・rename・削除・実行はしない。
- 出力先が共有フォルダ内なら起動時に拒否する。
- bag / db3 / mcap / 動画 / PCD本体は読まない（PCDはヘッダ11行のみ）。
- テスト: フィクスチャで実行前後の SHA256 一致を確認済み。

出力（`OUT/`）:

| ファイル | 内容 |
|---|---|
| `FILE_INVENTORY.csv` | 全ファイルのpath / ext / size / mtime / category / state(failed・success・backup) / relevance |
| `HITS.csv` | 検出器フラグ、calib flags、K/D、extrinsic、sync、z-buffer、PCD I/O 等のキーワード該当行（ファイル・行番号付き） |
| `extracted/` | 高価値テキスト（≤512KB）の原文コピー、docx/pptx/xlsx のテキスト、PDF、PCDヘッダ |
| `IMAGES.csv` | 画像一覧（中身はコピーしない） |
| `SUMMARY.txt` | 拡張子・カテゴリ別件数、読み取りエラー |
| `legacy_audit_bundle.zip` | 上記一式 |

## Step 2 — 解析セッションに渡す

`legacy_audit_bundle.zip` をこのリポジトリの `LEGACY_LVISAM_AUDIT/input/` にコミットするか、
セッションに添付する。加えて、`IMAGES.csv` から以下に該当する画像を最大10〜20枚ほど選んで添付すると、目視で確かめるべき項目を確認できる:
チェッカーボード実物 / 撮影シーン / LiDAR-camera マウント / 投影オーバーレイ / 色付き点群スクリーンショット。

## Step 3 — 監査（収集物を受け取ってから）

Phase 2〜6 を実施し、`REPORT.md` `EVIDENCE_TABLE.csv` `CURRENT_VS_LEGACY.md`
`REUSE_ASSESSMENT.md` `NEXT_PLAN.md` を作成する。各 CLAIM には evidence level
（OBSERVED / INFERRED / UNKNOWN / CONFLICT / DO NOT USE AS CURRENT VALUE）を付ける。
