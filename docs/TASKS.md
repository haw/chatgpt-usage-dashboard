# タスクリスト

## 集計CSV版MVP

- [x] CSV版の仕様とデータ境界を文書化する
- [x] 2種類のCSVの検証・正規化・日付結合を実装する
- [x] raw CSV保存と日付単位の冪等保存を実装する
- [x] CSVアップロードAPIを実装する
- [x] ワークスペース全体向け集計とロバスト異常判定を実装する
- [x] アップロード、KPI、推移、アラート、日次表を画面へ実装する
- [x] CSV取込・異常判定・APIのテストを追加する
- [x] READMEとDocker構成をCSV版へ更新する
- [x] Docker Composeでテストと画面動作を確認する

## AWS化

- [ ] S3ストレージアダプターを追加する
- [ ] ECS/FargateまたはLambdaの費用比較後に実行基盤をIaC化する
- [ ] CloudFront、S3、API Gateway、CognitoをIaC化する
- [ ] GitHub Actions OIDCとAWSデプロイを構成する
- [ ] 保持期間、暗号化、監視、アラートを設定する

## 旧Analytics API版（参考・実環境未確認）

- [x] Analytics APIクライアントと7日分の手動収集CLIを実装する
- [x] APIレスポンスのraw保存と正規化を実装する
- [ ] 利用可能な契約・権限を得た場合に実APIで検証する
