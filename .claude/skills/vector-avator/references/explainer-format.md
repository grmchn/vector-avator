# 解説動画のデータ形式：内容・台本・意味タグ

解説動画のデータを、キャラに依存しない「内容」と、キャラに依存する「台本」「演技」に分けます。見本は `data/explainer/samples/agi_singularity/`（内容 `content.json`、仮うさぎの台本 `script.usagi.json`）です。動きのルールは `motion-rules.md`、キャラ定義は `avatar-package.md` を参照してください。

## 1. 3 層の分け方

解説動画のデータを、キャラに依存しない「内容」と、キャラに依存する「台本」「演技」に分ける。キャラを差し替えるときは、内容をそのまま使い、台本と演技だけを作り直す。

```
内容層 content.json          何を伝えるか。キャラに依存しない
  │                          行ごとの要旨・必ず言う語・画面に出すもの・意味タグ・感情
  │  キャラの口調で書き直す
  ▼
台本層 script.<キャラ ID>.json  どう言うか。キャラに依存する
  │                          行ごとの字幕・読み・かな、意味タグの語句の位置
  │  意味タグをキャラの癖で身振り・表情・声に変える
  ▼
演技層（生成物）              どう動くか。モーション・口パク・音声（build_timeline.py が作る。保存しない）
```

HTML と CSS にたとえると、意味タグがクラス、キャラのパッケージがスタイルシートにあたる。キャラの差し替えは、スタイルシートの差し替えで済むようにする。

置き場所は `data/explainer/<内容 ID>/` とし、内容層 1 つと、キャラごとの台本層を置く。見本は `data/explainer/samples/<内容 ID>/` に置く。

## 2. 内容層 `content.json`

```json
{
  "format": "explainer-content",
  "version": 1,
  "id": "agi_singularity",
  "title": { "ja": "AGI・RSI・シンギュラリティをかるく説明" },
  "lines": [
    {
      "id": "L03",
      "scene": "agi",
      "visual": { "image": "agi", "text": { "ja": "AGI ＝ 汎用人工知能" } },
      "gist": "1 つめ：AGI は「汎用人工知能」。人間のように、いろいろな分野の知的な仕事をこなせる AI のこと",
      "terms": ["AGI", "汎用人工知能"],
      "emotion": "calm",
      "tags": [
        { "tag": "enumerate", "n": 1 },
        { "tag": "point_at", "region": "card" },
        { "tag": "emphasize", "term": "汎用人工知能" }
      ],
      "seconds": 6.0,
      "reference": { "ja": "ひとつめ、AGI は、汎用人工知能。人間のように、いろいろな分野の仕事をこなせる AI のことです。" }
    }
  ]
}
```

| 項目 | 必須 | 内容 |
|---|---|---|
| `format`・`version` | ○ | `explainer-content`・`1` |
| `id` | ○ | 内容 ID（英小文字・数字・`_`） |
| `title` | ○ | 題名（言語ごと） |
| `lines[].id` | ○ | 行 ID（`L01` など）。台本層はこの ID で行を対応させる |
| `lines[].scene` | ○ | 場面 ID。場面が変わると間が長くなり、画面の絵が替わる |
| `lines[].visual` | | 画面に出すもの：`image`（画像 ID）、`text`（文字）、`clip`（場面の演出 ID）のいずれか・組み合わせ |
| `lines[].gist` | ○ | 伝える内容の要旨。台本はこれを変えずに言い方だけを変える |
| `lines[].terms` | | 台本で必ず言う語（言い換えない用語・固有名詞）。語句に付くタグの目印にもなる |
| `lines[].emotion` | | 感情（§4）。省略時は `calm` |
| `lines[].tags` | | 意味タグ（§3） |
| `lines[].seconds` | | 読み上げの長さの目安（秒）。台本の書き直しはこれから大きく外さない |
| `lines[].reference` | | 元の言い回し（言語ごと）。書き直しの参考で、キャラに依存してよい |
| `lines[].note` | | 書き直す人への注意（例：「キャラ名を名乗る」） |

キャラに依存する言い回し（一人称・語尾・キャラ名）は `gist` に書かない。キャラ名を言わせたい行は、`gist` に「自分の名前を名乗る」と書き、`terms` には入れない。

### 2.1 画面の図 `images.json`

内容層の `visual.image` の図は、内容層と同じフォルダの `images.json`（共通の画風の指示と、画像 ID ごとの指示）から Codex imagegen で作る。図はキャラに依存しない。

```bash
.venv/bin/python tools/explainer/make_images.py data/explainer/samples/<内容 ID>   # → var/explainer/images/<内容 ID>/<画像 ID>.png（コミットしない）
```

画像には文字を入れない（生成画像の日本語は崩れやすい）。合成（`simple_compose.py`）が、図の下に `visual.text` を添えたカードにする。図がない行は `visual.text` だけのカードになる。

## 3. 意味タグ

### 3.1 語彙

| タグ | 意味 | 引数 | 既定の身振り（§5） | 演技の例（キャラの癖で変わる） |
|---|---|---|---|---|
| `greet` | あいさつ | | `spread` | 手を振る、両手を広げる |
| `introduce` | 話題の提示・予告 | | `explain` | 手のひらを上にして差し出す |
| `enumerate` | n 番目の列挙 | `n`（1 から） | `explain` | 指で数える、指差し |
| `emphasize` | 強調 | | `spread` | 両手を広げる、拳。語句に付けると声に合わせたビートが強くなる（M12） |
| `point_at` | 画面のものを指す | `region`（`tools/explainer/layout.json` の領域。省略時は画面の絵全般） | `point` | 指差し。領域があれば腕の IK でそこへ向ける（M11） |
| `question` | 問いかけ | | `nod`（首かしげ） | 首をかしげる |
| `think` | 考える・溜め | | `think` | 顎に手 |
| `surprise` | 驚き | | `surprise` | 驚き顔、のけぞる |
| `agree` | 同意・肯定・念押し | | `nod` | うなずき |
| `contrast` | 対比（A と B） | | `explain` | 左右の手を順に出す |
| `conclude` | まとめ | | `nod` | 両手を胸の前で合わせる、うなずく |
| `demo` | 機能を体で見せる | `motion`（`turn`＝首振り、`idle`＝待機の呼吸・まばたき） | 引数のモーション | キャラに依存しない（見せたい動きそのもの） |

語彙にない演技が要るときは、まず語彙を足す（本書を更新する）。1 回限りの演技は、台本層の `override`（§6.3）で書く。

### 3.2 強さと位置

| 項目 | 値 | 内容 |
|---|---|---|
| `strength` | `weak`・`mid`（既定）・`strong` | 演技の大きさ。キャラの癖の倍率に掛ける |
| `at` | `line`（既定）・`start`・`end` | 行全体・行頭・行末に付く |
| `term` | `terms` の 1 語 | 語句に付く。台本層の `anchors` が、その語を台本のどこで言うかを示す |

`term` を持つタグは語句のタグ、持たないタグは行のタグである。1 行の身振りは、行のタグのうち最初のものから決める（§5）。語句のタグは、身振りの形を変えずに上から重ねる（`emphasize` の語句はビートを強くする）。

### 3.3 バストアップの小窓での型と小物

`build_timeline.py --acting ...,bust` のとき、行の**最初の**タグで頭の上の小物と身振りの型が決まる（`docs/motion-rules.md` M23、`tools/explainer/bust.py`）。

| 最初のタグ | 小物（部品のグループ `prop`） | 身振りの型 |
|---|---|---|
| `question`・`think` | `question`（「？」） | あごに手（`think_r`） |
| `introduce`・`emphasize`・`conclude` | `idea`（電球） | 顔の横へ腕を上げる（`idea_r`・`idea_l`） |
| それ以外 | なし | 通常の身振り（腕は小窓に入るように上げる） |

小物の部品がないキャラでは、小物は出ない（身振りの型だけが付く）。

## 4. 感情

表情は感情で書き、表情 4 種への割り当ては演技層で行う（キャラの癖で変えられるようにするため）。既定の割り当ては次のとおり。

| 感情 `emotion` | 意味 | 既定の表情 |
|---|---|---|
| `calm` | 平静（既定） | `neutral` |
| `joy` | 喜び・楽しさ | `smile` |
| `surprise` | 驚き | `surprised` |
| `trouble` | 困り・心配 | `troubled` |

## 5. 既定の変換（タグ → 身振り・表情）

キャラの癖を入れる前の、キャラに依存しない既定の変換である。`tools/explainer/explainer_format.py` の `to_legacy()` が、内容層と台本層から、今の道具（`build_timeline.py`）が読む行（`gesture`・`expr`・`icon`・`scene`・`point_at`・`emphasize`）を作る。

1. `gesture`：行のタグのうち最初のものを、§3.1 の「既定の身振り」に変える。行のタグがなければ `explain`（中立の説明）。`demo` は引数のモーション名。
2. `expr`：§4 の既定の表情。
3. `point_at`：`point_at` タグの `region`。
4. `emphasize`：語句に付いた `emphasize` タグの語の、台本層の `anchors` のかな（G12 の `beats.py` が読む形）。
5. `icon`・`scene`：内容層の `visual.image` と `scene`。
6. 台本層の行に `override` があれば、最後にそれで上書きする。

## 6. 台本層 `script.<キャラ ID>.json`

```json
{
  "format": "explainer-script",
  "version": 1,
  "content": "agi_singularity",
  "char": "a twin-tail character",
  "lines": [
    {
      "id": "L03",
      "ja": "ひとつめ、AGI は汎用人工知能です。人間みたいに、いろんな分野のお仕事ができる AI なんです。",
      "ja_tts": "ひとつめ、エージーアイは汎用人工知能です。人間みたいに、いろんな分野のお仕事ができるエーアイなんです。",
      "ja_kana": "ひとつめ えーじーあいは はんようじんこうちのうです にんげんみたいに いろんなぶんやの おしごとができる えーあいなんです",
      "anchors": {
        "汎用人工知能": { "ja": "汎用人工知能", "kana": "はんようじんこうちのう" }
      }
    }
  ]
}
```



### 6.1 項目

| 項目 | 必須 | 内容 |
|---|---|---|
| `format`・`version` | ○ | `explainer-script`・`1` |
| `content` | ○ | 内容 ID |
| `char` | ○ | キャラ ID（`data/characters/<id>.json`） |
| `note` | | 台本の由来など |
| `lines[].id` | ○ | 内容層の行 ID。内容層の行と同じ数・同じ順に並べる |
| `lines[].ja` | ○ | 字幕 |
| `lines[].ja_tts` | ○ | TTS に渡す文（数字の読み・読み間違いの直しを入れる） |
| `lines[].ja_kana` | ○ | ひらがなの読み（口パクと強調語の位置に使う。カタカナ・漢字を入れない） |
| `lines[].en`・`en_tts` | | 英語版 |
| `lines[].anchors` | 条件付き | 語句のタグの語（`term`）ごとに、台本でその語を言う部分：`ja`（字幕の部分文字列）と `kana`（`ja_kana` の部分文字列）。内容層で語句のタグが付いた語はすべて必要 |
| `lines[].override` | | 上書き（§6.3） |

### 6.2 書き直しで守ること

- 内容層の行を足したり消したりしない。行の順も変えない。
- `terms` の語は言い換えない。語句のタグの語は `anchors` で位置を示す。
- 長さは `seconds` の目安から大きく外さない。

### 6.3 上書き `override`

タグの既定の変換と違う身振り・表情を使いたい行だけに書く。値は今の台本と同じ `gesture`（`spread`・`nod`・`surprise`・`explain`・`point`・`think`・`turn`・`idle`）と `expr`（`neutral`・`smile`・`surprised`・`troubled`）。キャラに依存する演技なので台本層に置く。

既存の台本を 3 層に移した見本では、元の身振り・表情をそのまま再現するため、既定の変換と違う行に `override` を付けている（§8）。

## 7. 検査と変換 `tools/explainer/explainer_format.py`

```bash
.venv/bin/python tools/explainer/explainer_format.py check data/explainer/samples/<内容 ID>        # Schema と内容の検査
.venv/bin/python tools/explainer/explainer_format.py legacy data/explainer/samples/<内容 ID> <キャラ ID> -o script.json   # 今の台本の形へ変換
```

JSON Schema は `tools/explainer/schema/content.schema.json`・`script.schema.json`。Schema では書けない次の点も検査する。

- 行 ID の重複、台本層の行が内容層と同じ数・同じ順か。
- タグの引数（`enumerate` の `n`、`demo` の `motion`、`point_at` の `region` が `layout.json` にあるか）、語句のタグの語が `terms` にあるか。
- 台本層の `anchors`：語句のタグの語がすべてあり、`ja`・`kana` が字幕・かなの部分文字列か。`ja_kana` がひらがな（と空白・句読点）だけか。
- キャラ ID が `data/characters/` にあるか。

## 8. 見本

| 内容 ID | 内容 | 行数 | 台本層 |
|---|---|---|---|
| `vector_howto` | ベクター立ち絵の作り方の紹介（`visual.clip` の演出は公開していないので、文字のカードで出る） | 17 | 仮うさぎの台本 |
| `agi_singularity` | AGI・RSI・シンギュラリティをかるく説明する | 11 | 3 キャラの台本 |

黒い太線のキャラの 8 つの価値は、別の人から頼まれて作ったものなので、見本にも他のキャラの動画にも使わない。


## 9. 台本の書き直し

### 9.1 手順

```bash
.venv/bin/python tools/explainer/make_script.py brief <内容のフォルダ> <キャラ ID> -o <依頼文.md>   # 依頼文を組み立てる
#   → 依頼文を書き手（エージェント・サブエージェント）に渡し、<内容のフォルダ>/script.<キャラ ID>.json を書いてもらう
.venv/bin/python tools/explainer/make_script.py check <内容のフォルダ> [<キャラ ID> ...]     # 検査（エラー＝形式、警告＝書き直しの質）
.venv/bin/python tools/explainer/make_script.py compare <内容のフォルダ> usagi ツインテールのキャラ 毛の多いキャラ   # 同じ行をキャラ別に並べる
.venv/bin/python tools/explainer/read_check.py <内容のフォルダ> <キャラ ID>                    # パッケージの声で読み、ASR で読みを確かめる
```

依頼文のひな形は `tools/explainer/rewrite_brief.md`。パッケージの性格・口調（一人称、呼びかけ、語尾、口調、言わないこと、例文）と演技の方向、話速、内容層の各行（要旨・必ず言う語・強調する語・意味・感情・長さの目安・参考の言い回し・備考）が差し込まれる。

`make_script.py check` の警告は次のとおり。

| 警告 | 内容 |
|---|---|
| 長さ | かなのモーラ数を 1 秒あたり 6 モーラ（× キャラの話速）で割った長さが、内容層の `seconds` の 0.7〜1.3 倍を外れる |
| 一人称 | パッケージの一人称以外の一人称（ぼく・わたし・私・俺 など）が字幕にある |
| 必ず言う語 | 内容層の `terms` の語が字幕にない（`anchors` で別の表記を示していればよい） |
| TTS の英字 | `ja_tts` に英字・数字が残っている |
| 字幕の長さ | 字幕が 70 字を超える |

### 9.2 崩れやすい点

- **長さの目安が短すぎると、要旨が削られる。** 書き手は目安に収めようとして要旨の一部を落とす。目安は、参考の言い回しをかなに開いたモーラ数を 6 で割って決める。6 モーラ/秒は、行の中の間を 0.22 秒に縮めた長さ（`build_timeline.py --max-pause 0.22`）の実測。間を縮めない読み上げは 1〜3 割長い。
- **英字・数字の読み。** `ja_tts` には読みどおりに書く（`AGI` → `エージーアイ`、`RSI` → `アールエスアイ`、`2045 年` → `にせんよんじゅうご年`、`Fable 5.2` → `フェイブル、ゴーテンニ`）。`Fable 5.2` は読み方を指定しても ASR では「号転移」「ゴテンリ」と聞き取られることがあり、聞き取りにくい語である。
- **字幕だけの記号。** 毛の多いキャラの語尾の `w` は字幕だけに書き、`ja_tts`・`ja_kana` には入れない。キャラ名の英字（`毛の多いキャラ`）も、読みは `毛の多いキャラ`・`らまちゃん` と書く。
- **必ず言う語と口調のぶつかり。** 仮うさぎは「難しい漢語を言わない」ので、要旨の「知的な仕事」を「頭を使う仕事」と言い換えた。`terms` に入れた語は言い換えないが、`terms` 以外は口調を優先してよい。言い換えたくない語は `terms` に入れる。
- **空白を含む語。** `terms` に「1 時間ちょっと」「2045 年」のような半角空白入りの語を入れると、字幕にも空白が必要になる。字幕の表記を自由にしたいときは、空白なしの語を `terms` に入れる。
- **TTS の読みのくせ。** ある声では「やあ」が、2 回とも ASR で「いや」と聞き取られた。あいさつは「こんにちは」などにするか、`ja_tts` を調整する。
- **作業の分け方。** 複数の書き手（サブエージェント）を同じフォルダで同時に動かすと、互いの生成スクリプトを上書き・実行してしまうことがある。書き手ごとに作業フォルダを分け、書いてよいファイルを依頼文で限る。
