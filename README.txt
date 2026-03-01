===========================================================
  Photo Archive — 静的フォトアーカイブ生成ツール
===========================================================

■ 概要
  NAS上の写真フォルダを再帰スキャンし、サムネイル・閲覧用縮小版・
  HTMLギャラリーを自動生成する静的サイトジェネレータです。
  増分更新対応（SQLite台帳）で、差分だけを処理します。
  同一内容の重複写真（sha1ハッシュ）は自動でスキップされます。

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
  4. 仮想環境を使う場合（推奨）:
     python -m venv .venv
     .venv\Scripts\pip install Pillow

■ 実行方法

  A) 写真フォルダでダブルクリック実行（推奨）:
     → 下記「写真フォルダでダブルクリック運用」を参照

  B) ツール本体フォルダでダブルクリック実行:
     build_gallery.cmd をダブルクリック

  C) コマンドライン実行:
     python -m photo_archive build --config config.json

  D) コマンドラインでパス指定:
     python -m photo_archive build -i "\\NAS\share\photos" -o "\\NAS\share\gallery"

===========================================================
  ■ 写真フォルダでダブルクリック運用
===========================================================

  最も手軽な運用方法です。写真フォルダに起動用cmdを1つ置くだけで、
  そのフォルダを自動的に入力元として処理します。

  【構成イメージ】

    C:\tools\photo-archive\          ← ツール本体（ローカルPC）
      photo_archive\
      templates\
      assets_src\
      .venv\
      config.json                    ← output_root 等の設定

    \\NAS\share\photos\              ← 写真フォルダ（NAS）
      2024\
      2025\
      PhotoArchive_RunHere.cmd       ← これをダブルクリック！

  【セットアップ手順】

  1. ツール本体を任意のローカルフォルダに配置
     例: C:\tools\photo-archive\

  2. ツール本体フォルダに config.json を作成
     - input_root は空でOK（起動時に自動設定される）
     - output_root は必ず設定すること

  3. PhotoArchive_RunHere.cmd をテキストエディタで開き、
     先頭の TOOL_HOME を編集：

       set "TOOL_HOME=C:\tools\photo-archive"

     .venv を使わない場合は PYTHON も変更:

       set "PYTHON=python"

  4. 編集した PhotoArchive_RunHere.cmd を写真フォルダにコピー

  5. 写真フォルダ内の PhotoArchive_RunHere.cmd をダブルクリック

  【config.json の探索順序】

  起動時、以下の順序で config.json を探します:
    優先1: 写真フォルダ（cmdと同じフォルダ）の config.json
    優先2: ツール本体フォルダ（TOOL_HOME）の config.json

  写真フォルダごとに異なる設定を使いたい場合は、
  そのフォルダに config.json を置けば個別設定が使えます。

  【注意事項】

  - config.json の input_root は起動時に自動上書きされます
    （cmdが置かれたフォルダが常に input_root になる）
  - output_root は必ず config.json で指定してください
  - ツール本体を写真フォルダにコピーする必要はありません
  - ロックファイルは output_root 側に作られます
  - 写真ファイルは一切改変されません（読み取り専用アクセス）

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
      manifest.sqlite    ... 増分管理用台帳（sha1含む）
    logs/
      run.log            ... 実行ログ（重複スキップ記録含む）
      errors.log         ... エラー詳細
    locks/
      build.lock         ... 同時実行防止ロック

■ 増分更新の仕組み
  - manifest.sqlite に全ファイルの relative_path / size / mtime / sha1 を記録
  - 次回実行時、変化があったファイルだけ再処理
  - 入力から消えたファイルは「削除扱い」（HTMLから除外）
  - --rebuild で全件再処理可能

■ 重複検出の仕組み
  - 新規ファイルのみ sha1 ハッシュを計算
  - 既存ファイルは size/mtime での差分判定（ハッシュ不要）
  - 同一 sha1 がアクティブ台帳にあれば「重複」としてスキップ
  - 同一 sha1 が「削除済み」にあれば「ファイル移動」と判定し、
    新しいパスを正として採用
  - スキップされた重複は logs/run.log に記録
  - 重複ファイルは metadata.json / HTML には載りません

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

  Q: 重複がスキップされたか確認したい
  A: logs/run.log に [DUPLICATE] として記録されています。
     ビルド完了時のサマリにも「重複: N」と表示されます。

  Q: TOOL_HOME のパスにスペースが含まれる
  A: 問題ありません。パスはダブルクォートで囲まれています。
     例: set "TOOL_HOME=C:\My Tools\photo-archive"

■ PyInstaller でのEXE化（任意）
  pip install pyinstaller
  pyinstaller --onefile --name PhotoArchive photo_archive/__main__.py
  生成された dist/PhotoArchive.exe を config.json と同じフォルダに置く

■ ライセンス
  MIT License

===========================================================
