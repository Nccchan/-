# 買取明細PDF生成プロジェクト

## プロジェクト概要
買取明細（支払通知書）をPDF形式で生成するPythonスクリプト。
ReportLabライブラリを使用してA4サイズのPDFを作成する。

## 技術スタック
- Python 3
- ReportLab（PDF生成）
- JSON（番号管理・データ保存）

## ディレクトリ構成
```
./
├── generate_receipt.py     # メインスクリプト
├── .receipt_counter.json   # 発行番号の管理ファイル（自動生成）
├── CLAUDE.md               # このファイル
└── .claude/
    ├── settings.json       # プロジェクト設定
    └── commands/           # カスタムコマンド
```

## 開発ルール
- スクリプトは1ファイルでシンプルに保つ
- 発行者情報（ISSUER）は定数として先頭にまとめる
- PDFのレイアウト変更は既存スタイルを継承して行う
- 番号管理ファイル（.receipt_counter.json）は直接編集しない

## よく使うコマンド
```bash
# PDF生成の実行
python3 generate_receipt.py

# 依存パッケージのインストール
pip3 install reportlab
```

## 注意事項
- .receipt_counter.json は自動管理されるため、Gitで追跡する必要はない（.gitignoreに追加済み）
- PDFの出力先はスクリプトと同じディレクトリ
- 日本語フォントはUnicodeCIDFont（HeiseiMin-W3）を使用
