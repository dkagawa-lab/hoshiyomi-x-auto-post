# HOSHIYOMI X自動投稿

HOSHIYOMI公式Xアカウント向けに、当日の天体イベントを計算し、投稿文を作成して1日4回自動投稿するサーバーレス構成です。朝は今日の星の流れから12星座別の運気とやるべきことを、夜は12星座別の振り返りをスレッド投稿します。GitHub Actionsだけで動きます。

## 構成

- Python 3.12
- GitHub Actions cron
- `pyswisseph` による天体計算
- Claude APIによる投稿文作成
- X API v2へのOAuth 1.0a投稿

外部エフェメリスファイルは不要です。`swe.FLG_MOSEPH | swe.FLG_SPEED` を使います。

## 投稿タイミング

| JST | UTC cron | 内容 |
|---|---:|---|
| 00:00 | `0 15 * * *` | 日付が変わった直後の今日の星 |
| 08:00 | `0 23 * * *` | 今日の星の流れと12星座別の運気・やること |
| 12:30 | `30 3 * * *` | 占星術の豆知識 |
| 22:00 | `0 13 * * *` | 今日の星のふり返りと12星座別の受け止め方 |

## X APIの準備

1. [X Developer Platform](https://developer.x.com/) で開発者アカウントを作成します。
2. Project / App を作成します。
3. App permissions を必ず **Read and write** に変更します。
4. 権限変更後に **Access Token and Secret を再生成** します。
5. Developer Console の **Billing & credits** で、投稿APIを使えるクレジット/課金状態になっていることを確認します。

注意: 権限を変更する前に発行したAccess Tokenでは投稿できません。Read and writeへ変更したあと、必ずトークンを作り直してください。

`402 Payment Required` が出る場合、キーの形式ではなくX API側のクレジット/課金設定で止まっています。Developer ConsoleでBilling & creditsを確認してください。

## GitHub Secrets

GitHubのリポジトリで `Settings` → `Secrets and variables` → `Actions` → `New repository secret` から登録します。

### X用

| Secret名 | 用途 | 必須 |
|---|---|---|
| `X_API_KEY` | X API Key | 本投稿時に必須 |
| `X_API_SECRET` | X API Key Secret | 本投稿時に必須 |
| `X_ACCESS_TOKEN` | Access Token | 本投稿時に必須 |
| `X_ACCESS_SECRET` | Access Token Secret | 本投稿時に必須 |
| `ANTHROPIC_API_KEY` | 投稿文作成。未設定ならテンプレート文にフォールバック | 任意 |

`SITE_URL` はワークフロー内で `https://hoshiyomi4u.com/m` を渡しています。

### Instagram用

Instagramはテキストだけでは投稿できないため、`instagram_post.py` が1080×1350の画像カードを生成し、Supabase Storageへアップロードした公開URLをInstagram Graph APIへ渡します。

| Secret名 | 用途 | 必須 |
|---|---|---|
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | `instagram_business_account.id` | Instagram本投稿時に必須 |
| `META_ACCESS_TOKEN` | Graph API用アクセストークン | Instagram本投稿時に必須 |
| `SUPABASE_URL` | Supabase Project URL | Instagram本投稿時に必須 |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Instagram本投稿時に必須 |
| `SUPABASE_BUCKET` | Storage bucket名。例 `instagram-posts` | Instagram本投稿時に必須 |
| `ANTHROPIC_API_KEY` | キャプション作成。未設定ならテンプレート文にフォールバック | 任意 |

Supabase StorageにはPublic bucketを作成してください。

```text
Bucket name: instagram-posts
Public bucket: ON
```

`META_ACCESS_TOKEN` は、Meta Graph API Explorerで取得したトークン、または `me/accounts` のレスポンスに含まれるFacebookページの `access_token` を使います。

`META_ACCESS_TOKEN has expired` または `Session has expired` が出た場合は、Meta側のアクセストークンが期限切れです。Graph API Explorerで再発行し、必要な許可を付けたうえで、GitHub Repository secret の `META_ACCESS_TOKEN` を更新してください。短期トークンはすぐ失効するため、運用ではMetaのアクセストークンツールで長期トークンへ交換してから登録することを推奨します。

必要な許可:

```text
instagram_basic
instagram_content_publish
pages_show_list
pages_read_engagement
```

## ローカル実行

```bash
pip install -r requirements.txt
DRY_RUN=1 python generate_and_post.py midnight
DRY_RUN=1 python generate_and_post.py morning
DRY_RUN=1 python generate_and_post.py noon
DRY_RUN=1 python generate_and_post.py night
```

引数を省略すると、現在時刻から `midnight` / `morning` / `noon` / `night` を自動判定します。

APIキーが一切ない環境でも、`DRY_RUN=1` ならテンプレートモードで文面を出力できます。

`morning` と `night` は5投稿のスレッドとして出力します。`morning` は1件目が今日の星の概要、2〜5件目が3星座ずつの運気とやるべきことです。`night` は1件目が今日の星の振り返り、2〜5件目が3星座ずつの振り返りと、できなかった時の受け止め方です。

Instagram用の画像生成テスト:

```bash
DRY_RUN=1 python instagram_post.py midnight
DRY_RUN=1 python instagram_post.py morning
```

生成画像は `out/` に保存されます。

## GitHub Actionsでのテスト

### X

1. Actionsタブを開きます。
2. `HOSHIYOMI X auto post` を選択します。
3. `Run workflow` を押します。
4. `dry_run` は最初は `1` のまま実行します。
5. ログに投稿文が出ることを確認します。
6. 本投稿テストをする場合だけ `dry_run` を `0` にします。

### Instagram

1. Actionsタブを開きます。
2. `HOSHIYOMI Instagram auto post` を選択します。
3. `Run workflow` を押します。
4. `dry_run` は最初は `1` のまま実行します。
5. 必要なら `slot` に `midnight` / `morning` / `noon` / `night` を入力します。
6. ログにキャプションと画像パスが出ることを確認します。
7. 本投稿テストをする場合だけ `dry_run` を `0` にします。

## テスト

```bash
python -m unittest discover
```

最低限、黄経から星座への変換と、350度から10度へ進むような角度ラップ時の通過判定を検証しています。

## 運用上の注意

- Xの自動化ラベル設定を推奨します。公式アカウントのプロフィール設定で、自動化アカウントであることを明示してください。
- 同一文面の連続投稿はXの重複コンテンツ・スパム扱いになる可能性があります。テンプレートモードだけで長期運用する場合は、投稿文のパターン追加を推奨します。
- 投稿文は断定や効果保証を避ける設計にしていますが、運用初期は必ずログを目視確認してください。
- 新月・満月・星座移動・逆行開始/終了がある日は、そのイベントを優先して扱います。
- Instagramは画像URLが外部から読める必要があるため、Supabase bucketはPublicにしてください。
