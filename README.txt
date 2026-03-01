===========================================================
  Photo Archive — 静的フォトアーカイブ生成ツール
===========================================================

■ 概要
  NAS上の写真フォルダを再帰スキャンし、サムネイル・閲覧用縮小版・
  HTMLギャラリーを自動生成する静的サイトジェネレータです。
  増分更新対応（SQLite台帳）で、差分だけを処理します。

■ 必要環境
  - Python 3.9 以上
  - Pillow ライブラリ（pip install Pillow）

■ セットアップ
  1. config.example.json を config.json にコピー
  2. config.json を編集:
     - input_root:  写真が入っているNASフォルダ（UNCパス可）
     - output_root: ギャラリーを出力するNASフォルダ（UNCパス可）
  3. Pillow をインストール:
     pip install Pillow

■ 実行方法

  A) ダブルクリック実行:
     build_gallery.cmd をダブルクリック

  B) コマンドライン実行:
     python -m photo_archive build --config config.json

  C) コマンドラインでパス指定:
     python -m photo_archive build -i "\\NAS\share\photos" -o "\\NAS\share\gallery"

■ コマンドラインオプション
  --config, -c     設定ファイルパス（デフォルト: config.json）
  --input, -i      入力パス（config より優先）
  --output, -o     出力パス（config より優先）
  --thumb-size     サムネイル長辺 px（デフォルト: 360）
  --view-size      閲覧用画像長辺 px（デフォルト: 1600）
  --include-heic   HEIC ファイルも処理する
  --hide-gps       GPS 情報を出力から除外する
  --rebuild        全ファイル再処理（増分無視）
  --use-temp PATH  一時ディレクトリを使う（ローカルSSD推奨）
  --open           完了後 index.html を開く（デフォルト ON）
  --no-open        完了後 index.html を開かない

■ 出力フォルダ構成
  output_root/
    index.html           ... トップページ（最近の写真）
    YYYY/MM/index.html   ... 月別ページ（日別セクション付き）
    assets/              ... CSS / JavaScript
    thumbnails/          ... サムネイル画像（長辺360px）
    views/               ... 閲覧用縮小版（長辺1600px）
    data/
      metadata.json      ... 全写真メタデータ（検索用）
      manifest.sqlite    ... 増分管理用台帳
    logs/
      run.log            ... 実行ログ
      errors.log         ... エラー詳細
    locks/
      build.lock         ... 同時実行防止ロック

■ 増分更新の仕組み
  - manifest.sqlite に全ファイルの relative_path / size / mtime を記録
  - 次回実行時、変化があったファイルだけ再処理
  - 入力から消えたファイルは「削除扱い」（HTMLから除外）
  - --rebuild で全件再処理可能

■ よくある失敗と対処

  Q: 「ロックファイルがあります」と表示される
  A: 前回ビルドが異常終了した可能性があります。
     output_root/locks/build.lock を手動削除してください。
     （2時間以上古いロックは自動削除されます）

  Q: NASの写真が読めない
  A: NASがマウントされているか確認してください。
     転送中のファイルは自動リトライ（0.5秒×3回）されます。

  Q: HEIC ファイルが処理されない
  A: config.json で "include_heic": true に設定してください。
     Pillow の HEIC 対応が必要です（pillow-heif パッケージ）。

  Q: EXIFが無い写真の日付がおかしい
  A: EXIFが無い場合、ファイルの更新日時（mtime）を使います。
     NASコピー時に mtime が変わることがあります。

  Q: ギャラリーがブラウザで正しく表示されない
  A: file:// プロトコルでの表示を前提にしています。
     ブラウザのセキュリティ設定でローカルファイルアクセスが
     制限されている場合があります。

■ PyInstaller でのEXE化（任意）
  pip install pyinstaller
  pyinstaller --onefile --name PhotoArchive photo_archive/__main__.py
  生成された dist/PhotoArchive.exe を config.json と同じフォルダに置く

■ ライセンス
  MIT License

===========================================================
