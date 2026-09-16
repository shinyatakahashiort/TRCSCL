# 最初にお読みください｜トーリックSCL軸選択アプリ

## このアプリでできること

装用前の矯正 S/C/Axis、現在のトーリックSCLの表示 S/C/Axis、実際の回転方向と回転量、SCL装用下の残余屈折 S/C/Axis を入力し、次に試すレンズの表示軸を比較します。

初期設定では、**現在と同じS/C・同じ回転を仮定し、軸だけを変更**します。表示軸を変更した際の残余乱視、残余球面度数、残余軸、回転変動の影響を計算します。

**本版は教育・研究用の臨床未検証プロトタイプです。数学的なテストの合格は臨床的有効性や処方の妥当性の検証を意味しません。**

## 1. GitHubとStreamlitで動かす

クラウドで使う場合、手元のパソコンにPythonをインストールする必要はありません。ブラウザからGitHubにコードを置き、Streamlit Community Cloudでそのコードを実行します。[1,2]

### GitHubへ配置

1. 配布ZIPを展開します。**ZIP自体をGitHubに置くだけでは動きません。**
2. GitHubにログインし、新しいリポジトリを作成します。名前の例は `toric-scl-axis-app` です。一般公開するコードに患者情報は含めないでください。
3. 展開したフォルダの「中身」をリポジトリのルートへアップロードします。画面により `uploading an existing file` または `Add file → Upload files` から操作します。
4. 少なくとも、以下の5ファイルが同じ階層にあることを確認します。

```text
app.py
engine.py
optics.py
visuals.py
requirements.txt
```

`README.md`、`tests/`、`docs/`、`.streamlit/`、`.github/`も一緒に配置できます。隠しフォルダのアップロードが難しい場合でも、上の5ファイルでアプリの基本機能は起動する構成です。`.streamlit/config.toml`を配置するとテーマ設定とコード側の使用統計送信無効化が適用されます。

### Streamlitで公開

1. Streamlit Community Cloudにログインし、GitHubアカウントを連携します。
2. `Create app` → 既存アプリを選択し、リポジトリ・ブランチ・実行ファイルを指定します。

| 設定 | 入力例 |
|---|---|
| Repository | 自分のアカウント / toric-scl-axis-app |
| Branch | main |
| Main file path | app.py |
| Advanced settings → Python | **3.12** |
| Secrets | 本アプリでは不要 |

3. `Deploy`を押します。[1]

`.python-version`だけでクラウドのPythonが選ばれるとは限らないため、**Advanced settingsで3.12を選んでください。**

一段上のフォルダごとアップロードした場合は、その階層を含む実行ファイルパス（例：`toric-scl-axis-app/app.py`）が必要になります。初めての場合はルートに配置する方が分かりやすくなります。

### テストも実行する

`.github/workflows/tests.yml` と `tests/` を配置すると、GitHub ActionsでPython 3.12/3.13のテストを実行する設定になります。リポジトリでActionsが許可されている必要があります。配布時点では、このユーザーのGitHub上でActionsを実行したわけではありません。

**配布時の確認範囲：計算52件・グラフ生成4件が合格。Streamlit UIテスト9件は依存パッケージを導入できない作成環境のため未実行です。** 初回公開時にActionsと実画面での検証を行ってください。詳しくは `docs/VALIDATION.md` に記録しています。

## 2. アプリへの入力

### 01：装用前の矯正値

装用前の矯正S/C/Axisを入力します。プラス円柱表記も入力可能です。C=0の軸は空欄で構いません。

眼鏡面の屈折値は、その頂点間距離を設定します。角膜面へ既に換算してある値なら0 mmです。初期値12 mmは機器設定を確認する代わりにはなりません。

この値は主計算に加算せず、装用後から推定した必要矯正との整合性確認に使用します。

### 02：現在のSCL

容器・処方に記載されたS/C/Axisを、**マイナス円柱表記**で入力します。

Axisは実際の眼上軸ではなく、レンズの**表示軸**です。現在のSCLが球面（C=0）の場合は、本アプリの対象外として計算を停止します。

### 03：実際の回転

**検者が患者の正面から見て、時計回りを＋、反時計回りを−とします。右眼・左眼で符号を反転しません。**

- 時計回り10°：`時計回り（＋）` と `10` を入力。
- 反時計回り10°：`反時計回り（−）` と `10` を入力。

6時にある位置マークは、時計回りでは検者から見て左へ移動します。「時計回り」と「マークが右に見える」を混同しないでください。製品ごとの基準位置からの回転を読み取ります。位置マークそのものが円柱軸とは限りません。

装用後の屈折値を測定したときと同じ回転状態を入力してください。回転の安定・再現性が未確認／不安定の場合は、結果に注意が表示されます。[3]

### 04：装用後の残余屈折値

**SCLを装用したまま測定した追加矯正値（over-refraction）**を入力します。他覚的屈折／自覚的追加矯正を区別して記録できます。

裸眼時の屈折値、SCLを外して測った屈折値、SCL度数を加算済みの最終処方は入力しません。

装用後屈折値の測定面も設定します。オートレフの表示VDが12 mmなら12 mm、角膜面の値なら0 mmです。**装用前と装用後で別々に指定できます。**

### 05：次に試せる表示軸

10°・5°・1°刻み、または使用可能な軸の手入力ができます。刻み指定は製品在庫を保証しません。必ず使用する製品・S/Cの規格と照合してください。

詳細設定では、次レンズのS/Cや次の予測回転量を変えた仮想比較が可能です。度数・デザイン変更によって回転挙動が変わる可能性は、アプリだけでは判定できません。

最後に定義確認のチェックを入れ、計算ボタンを押します。入力を変えると古い結果は非表示になり、再計算が必要です。

## 3. 動作確認用のデモ

「時計回り10°のデモ」を押して、確認チェックと計算を実行してください。

| 入力項目 | 架空の値 |
|---|---|
| 装用前の必要矯正 | S −3.00 / C −1.25 × 180° |
| 装用前の頂点間距離 | 0 mm（角膜面） |
| 現在のSCL表示度数 | S −3.00 / C −1.25 × 180° |
| 回転 | 検者から見て時計回り10° |
| 実際の眼上光学軸 | 170° |
| 装用後の追加矯正 | 約 S +0.21706 / C −0.43412 × 40° |
| 装用後の頂点間距離 | 0 mm（角膜面） |

期待される表示軸は **10°**、次に同じ時計回り10°が生じたときの眼上軸は **180°**、理論上の残余乱視は **0.00 D** です。デモでは未丸め値を内部設定しています。

「反時計回り10°のデモ」は表示軸 **170°** になります。

もう1つの重要な確認：時計回り10°のデモで、装用後屈折をS=0/C=0に変更すると、主計算の表示軸は**180°のまま**になります。実測残余がゼロなら、既に矯正されている状態に単純な回転補正をもう一度かけないためです。装用前との不一致は別のタブで確認できます。

## 4. ローカルで動かす

Python 3.12を用意し、展開したフォルダで次を実行します。

```bash
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1 --server.headless=false
```

Mac / Linux：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address=127.0.0.1 --server.headless=false
```

Macで`python`が見つからない場合、最初のコマンドを`python3 -m venv .venv`にします。初回の依存パッケージ導入にはインターネット接続が必要です。

ブラウザが開かない場合は、実行画面に表示されるローカルURLを開きます。標準ポートの場合は `http://127.0.0.1:8501` です。

テストだけを実行する場合：

```bash
python -m unittest discover -s tests -v
```

`optics.py` と `engine.py` の計算部分はPython標準ライブラリのみで動作します。

## 5. データの扱いと運用範囲

本コードは患者名・IDの入力欄を持たず、入力値をDBへ保存せず、外部AI APIも使用しません。計算結果は操作中のセッションメモリに保持され、利用者がダウンロード操作をするとJSON/CSV/TXTに出力されます。

**Streamlit Cloudでは入力値がサーバーに送られます。** 「永続DBを使わない」と「端末外へ送信しない」は別です。実データでの運用前に施設の情報管理方針・クラウド利用条件・共有設定を確認してください。ホスティング基盤のログやアクセス解析まで本コードで完全に制御できるわけではありません。

臨床運用・第三者提供の前には、専門家による独立検算、入力ミスと回転符号の評価、実症例での前向きな再現性検証、必要な院内・制度上の確認を行ってください。「研究用」と表示することだけで臨床利用の適切性が保証されるわけではありません。

## 参考

[1] Streamlit公式：Deploy your app on Community Cloud  
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

[2] Streamlit公式：Connect your GitHub account  
https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account

[3] CooperVision Australia：Toric Fitting Guidelines  
https://coopervision.net.au/practitioner/fitting-tips-and-tools/toolkits/biofinity/toric-fitting-guidelines

[4] Thibos LN, Wheeler W, Horner D. Power vectors. Optom Vis Sci. 1997;74(6):367–375.  
https://pubmed.ncbi.nlm.nih.gov/9255814/

公式資料の参照日：2026年9月17日。本配布時点で、利用者のGitHubへの登録・Streamlitへの公開操作は実施していません。
