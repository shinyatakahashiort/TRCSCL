# Toric SCL Axis Planner

**トーリックソフトコンタクトレンズの残余乱視から、次に試す表示軸を比較する日本語Streamlitアプリ。**

> 教育・研究用／臨床未検証。処方確定用ではありません。

最初の導入と入力方法は **[START_HERE_JA.md](START_HERE_JA.md)** をご覧ください。

## 入力と出力

装用前の矯正S/C/Axis、装用中SCLの表示S/C/Axis、検者から見た時計回り／反時計回りと回転量、SCL装用下の残余屈折S/C/Axisを入力します。

**主計算：実際の眼上SCL ＋ 角膜面へ換算した装用後追加矯正 = 推定必要矯正。** 装用前の矯正は重ねて加算せず、独立した整合性確認に使います。Thibosのパワーベクトル表現を使用し、各候補SCLを差し引いた残余|C|を比較します。[1]

候補内で残余乱視が最小の表示軸、理論連続最適軸、予測眼上軸、残余S/C/Axis、軸変更だけで残る下限、次レンズの回転変動シナリオを表示します。結果はJSON/CSV/TXTで保存できます。

## 符号規約

検者が患者の正面から見て、時計回りを正とします。右眼・左眼で符号を反転しません。

```text
実際の眼上軸 = 現在の表示軸 − 時計回り正の回転量   (mod 180°)
次の表示軸   = 目標の眼上軸 ＋ 次の時計回り正の回転量 (mod 180°)
```

CooperVisionのCAAS（Clockwise Add / Anti-clockwise Subtract）と整合します。[2] 6時マークの移動方向と「時計回り」を混同しないでください。位置マークそのものが光学軸とは限りません。

## 起動

Python 3.12で、以下を実行します。

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address=127.0.0.1 --server.headless=false
```

GitHubへ配置してStreamlit Community Cloudへデプロイする場合は、エントリーポイントに`app.py`、Pythonに`3.12`を選択します。[3]

## ファイル構成

```text
app.py                      日本語UI・入力検証・古い結果の非表示
optics.py                   屈折ベクトル・頂点間距離・回転・最適化
engine.py                   主計算・整合性確認・JSON/CSV/TXT出力
visuals.py                  残余乱視曲線と検者正面視の軸図
requirements.txt            バージョン固定した直接依存パッケージ
START_HERE_JA.md             導入・入力・デモ・データ管理の説明
.streamlit/config.toml      テーマ等
.github/workflows/tests.yml GitHub Actionsの検証設定
examples/demo_cases.json    架空の計算例・期待値
examples/demo_cli.py        コマンドラインでの簡易検算
examples/clockwise_demo.txt デモ結果の説明
examples/clockwise_demo.json デモの全入力・全候補・計算結果
examples/clockwise_candidates.csv デモの候補一覧
tests/                      光学・計算フロー・グラフ・UIのテスト
docs/ALGORITHM.md           数式・仮定・限界
docs/VALIDATION.md          確認範囲と未確認事項
docs/TEST_LOG.txt           作成環境の実際のテスト記録
```

## 検証状況

作成環境では**52件の計算テストと4件のグラフ生成テストが合格**しました。Streamlitパッケージを導入できなかったため、**UIテスト9件はスキップしており、UIの実行合格とは扱っていません**。GitHub Actionsには依存パッケージ導入後にUIテストを実行する設定を含めていますが、ユーザーのリポジトリ上では未実行です。

```bash
python -m unittest discover -s tests -v
```

この数学的な検証と、実際の患者での臨床検証は別です。

## 主な設計上の制限

主結果は、**選択した次レンズのS/Cを固定した、角膜面における残余|C|最小化**です。S/Cを同時に最適化した処方ではありません。既定では現在と同じS/C・同じ回転を仮定します。次回転を変えた場合も推定必要矯正は固定し、現在の回転・屈折測定誤差までは伝播させません。

角膜・涙液・レンズ変形・偏心・高次収差・調節・瞳孔径・動的回転などはモデル化していません。RGP、オルソケラトロジー、トーリックIOLへの転用は想定していません。

アプリに患者名・IDは入力しないでください。クラウド運用時には屈折値等がサーバーへ送信されます。本コードはDB保存・外部API呼び出し・入力ログ出力を実装していませんが、ホスティング基盤全体のデータ保持を保証するものではありません。

## 参考資料

[1] Thibos LN, Wheeler W, Horner D. Power vectors: an application of Fourier analysis to the description and statistical analysis of refractive error. Optom Vis Sci. 1997;74(6):367–375. DOI:10.1097/00006324-199706000-00019. https://pubmed.ncbi.nlm.nih.gov/9255814/

[2] CooperVision Australia. Toric Fitting Guidelines. https://coopervision.net.au/practitioner/fitting-tips-and-tools/toolkits/biofinity/toric-fitting-guidelines

[3] Streamlit. Deploy your app on Community Cloud. https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

これらは光学表現・回転補正・実装基盤の参考であり、本アプリの臨床的有効性を検証した文献ではありません。
