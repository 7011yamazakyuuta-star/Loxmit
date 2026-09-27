# Loxmit

![Loxmit icon](kaperio/static/icon-64.png)

自分のファイル、または所有者の許可があるファイルのパスワード復元と、解除済みファイルの保存を行うローカルアプリです。原本は変更しません。文書やパスワードを外部サービスへ送信しません。

**0.4.0-alpha.11** / MITライセンス / 旧名称 Kaperio / Hashcat公式製品ではありません。

[ダウンロード](https://github.com/7011yamazakyuuta-star/Loxmit/releases) ·
[使い方・対応形式](kaperio/README.md) ·
[初回セットアップとGPU診断](kaperio/docs/SETUP.md)

alpha.9ではOfficeの展開量制限、LAN接続待ち対策、解析中の操作応答を改善し、文書解析を時間・メモリー制限付きの別プロセスに分離しています。[対策の範囲と制限](kaperio/docs/HARDENING.md)。公開済みパッケージの版と各OSの検証状況は、リリース説明を確認してください。

alpha.10では一時パスワード結果の例外時削除、文書補助処理の一時出力の集約、入れ子の一時ファイルの容量・件数制限を追加しました。各OSの配布ビルドでは、実際に導入されたPython依存を既知の脆弱性情報と照合します。[監査の範囲と制限](kaperio/docs/PRIVACY_AUDIT.md)。

alpha.11では、設定の「保護状態」から保存先のOS暗号化を照会できます。設定変更・管理者権限の要求・回復キー取得は行いません。文書ワーカーの環境変数継承も制限しました。[保護範囲と未対応事項](kaperio/docs/SECURITY_READINESS.md)。正式な署名・公証のビルド経路は追加しましたが、証明書未取得のため、配布版は引き続き未署名・未公証です。[署名手順](kaperio/docs/SIGNING.md)。

## はじめる

配布ファイルを展開して起動します。Pythonは不要です。画面は既定ブラウザーで開きます。フォルダー内の部品を削除せず、まとめて保管してください。

| OS | 配布ファイル末尾 | 起動 | Hashcatの準備 |
|---|---|---|---|
| Windows x64 | `windows-amd64.zip` | `Loxmit.exe` | 同意後、公式配布物を自動ダウンロード |
| macOS 15以降・Apple Silicon | `darwin-arm64.zip` | `Loxmit.app` | 同意後、同梱部品を自動展開 |
| macOS 15以降・Intel | `darwin-x86_64.zip` | `Loxmit.app` | 同意後、同梱部品を自動展開 |
| Linux x86-64 | `linux-x86_64.tar.gz` | `Loxmit/Loxmit` | 同意後、同梱部品を自動展開 |

Linuxの検証対象はUbuntu 22.04、glibc 2.35以降です。macOS／Linuxの自動準備にHomebrew、管理者権限、開発用コンパイラーは不要です。GPUドライバーは導入・更新しません。GPUランタイムの利用可否は環境に依存します。

1. 初回ガイドで必要な部品だけ準備し、GPU診断を実行します。既知パスワードで開く場合はHashcat不要です。
2. 自分のファイルを追加し、「パスワードを探す」または「パスワードが分かる」を選びます。
3. 復元されたパスワードをコピーするか、パスワードなしの文書を書き出します。

初期状態は空のライブラリーです。デモファイルは入りません。終了は右上の電源ボタンから行います。

## できること

- PDF・Excel・PowerPoint・Word・ZIPの対応する暗号形式の復元と解除。ZIP探索には別途 `zip2john` が必要です。
- おまかせ探索で、覚えている単語・文字数・文字種から候補を作成。「覚えていない」回答にも対応します。
- 詳細指定では辞書、マスク、変形、辞書とマスクの組合せ、段階探索に対応します。
- 16文字超の候補にも対応。形式ごとのUTF-8バイト上限と候補数上限があります。
- 1ファイル200 MiBまで取り込み。解除済みの元形式・画像PDF・画像Word・PNG・既存テキストを保存できます。変換対象は形式によります。
- チュートリアル、GPU診断、一時停止・再開、温度と時間の上限、結果のコピー。

復元の成功や、本家Hashcatより高速という保証はありません。[速度検証の条件と限界](kaperio/docs/PERFORMANCE.md)を公開しています。画像Wordは編集可能なOCR文書ではありません。Officeの画像化にはOfficeまたはLibreOfficeが別途必要です。

## 配布と検証

ストアは使わずGitHub Releasesで配布します。Windowsのコード署名、macOSのDeveloper ID署名・公証は未実施です。OSの警告が出る場合がありますが、セキュリティ機能を一括無効化しないでください。

GitHub Actionsでは4種類のネイティブアプリをビルドし、起動・復号・変換をテストします。macOS／Linuxでは同梱Hashcatの同意付き展開、バージョン照会、8種類の形式モジュール読込も検証します。**ビルド・起動成功と実GPUでの復元性能は別の確認です。** 結果は各リリースと[Actions](https://github.com/7011yamazakyuuta-star/Loxmit/actions/workflows/desktop.yml)で確認できます。

スマホ向けはPCを処理担当にするHTTPS遠隔操作の基盤のみです。iOS／Android単体の復元アプリや、ワンクリック接続は未提供です。

## 開発と安全性

ソース版はPython 3.12以降が必要です。Windowsでは `Setup.cmd` → `Loxmit.cmd`、macOS／Linuxでは `kaperio/setup.sh` → `kaperio/launch.sh` を使います。ソース版のネイティブHashcat部品は別途ビルドまたは手動設定します。

内部の `kaperio/` フォルダー、旧ランチャー、旧環境変数・保存場所には互換性を残しています。GitHubのリポジトリ名と公開製品名は **Loxmit** です。既存の個人データを勝手に移動・削除しません。

解除済み文書は暗号化されていません。保存先を適切に管理してください。パスワードの画面表示は一時的で、アプリ再起動時に消えます。

[ライセンス](LICENSE) · [第三者表示](kaperio/THIRD_PARTY.md) ·
[安全性](kaperio/SECURITY.md) · [配布・検証の詳細](kaperio/docs/DESKTOP.md) ·
[ソース配布手順](kaperio/docs/DISTRIBUTION.md)
