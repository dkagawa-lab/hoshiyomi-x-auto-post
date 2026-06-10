# HOSHIYOMI X自動投稿

HOSHIYOMI公式Xアカウント向けに、当日の天体イベントを計算し、投稿文を作成して1日4回自動投稿するサーバーレス構成です。GitHub Actionsだけで動きます。

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
| 07:30 | `30 22 * * *` | 今日の月星座と過ごし方 |
| 12:30 | `30 3 * * *` | 占星術の豆知識 |
| 21:00 | `0 12 * * *` | 今日のふり返りと明日への指針 |

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

| Secret名 | 用途 | 必須 |
|---|---|---|
| `X_API_KEY` | X API Key | 本投稿時に必須 |
| `X_API_SECRET` | X API Key Secret | 本投稿時に必須 |
| `X_ACCESS_TOKEN` | Access Token | 本投稿時に必須 |
| `X_ACCESS_SECRET` | Access Token Secret | 本投稿時に必須 |
| `ANTHROPIC_API_KEY` | 投稿文作成。未設定ならテンプレート文にフォールバック | 任意 |

`SITE_URL` はワークフロー内で `https://hoshiyomi4u.com/m` を渡しています。

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

## GitHub Actionsでのテスト

1. Actionsタブを開きます。
2. `HOSHIYOMI X auto post` を選択します。
3. `Run workflow` を押します。
4. `dry_run` は最初は `1` のまま実行します。
5. ログに投稿文が出ることを確認します。
6. 本投稿テストをする場合だけ `dry_run` を `0` にします。

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
