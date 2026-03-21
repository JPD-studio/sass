# マージ手順: コミット 73b877b の段階的統合

**目的**: GitHub コミット `73b877bc1b07` (チャンネルデータの開始位置修正) をローカルに安全にマージする

**ブランチ**: `feature/akira-saito` → 現在のブランチへ cherry-pick

**予想時間**: 15-30 分

---

## 概要

3 方向マージにより、以下のファイルが対象：

| ファイル | 状態 | アクション |
|---------|------|----------|
| `cepf_sdk/drivers/robosense_airy_driver.py` | ✅ 自動解決 | 何もしない |
| `tests/test_parsers/test_robosense_airy.py` | ✅ 自動解決 | 何もしない |
| `cepf_sdk/sources/airy_live.py` | ⚠️ コンフリクト | `git checkout --theirs` で一括採用 |
| `apps/run_pipeline.py` | 🔴 コンフリクト | 手動で 6 箇所を統合 |

---

## Phase 1: 準備

### 1.1 未コミット変更を退避

```bash
cd /home/jetson/repos/sass

# 現在の変更を確認
git status

# 一時保存（履歴には記録されない）
git stash

# 確認: ワーキングディレクトリが clean になった
git status
# On branch feature/nodejs-viewer-improvements
# nothing to commit, working tree clean ✅
```

**stash の内容を確認したい場合**:
```bash
git stash list
git stash show -p
```

---

### 1.2 新規ブランチを作成（安全性のため）

```bash
# 新しいブランチで作業（元のブランチは保護される）
git checkout -b merge/airy-driver-fix

# 確認
git branch
#   feature/nodejs-viewer-improvements
# * merge/airy-driver-fix
```

---

## Phase 2: マージ開始（コンフリクト発生）

### 2.1 cherry-pick コマンド実行

```bash
git cherry-pick 73b877b

# 予想される出力:
# Automatic merge failed
# CONFLICT (add/add): cepf_sdk/sources/airy_live.py
# CONFLICT (content): apps/run_pipeline.py
# Cherry pick stopped here
```

### 2.2 現在の状態を確認

```bash
git status

# 表示内容:
# On branch merge/airy-driver-fix
# You are currently cherry-picking commit 73b877b.
#   (fix conflicts and run "git cherry-pick --continue")
#
# Unmerged paths:
#   (use "git add/rm <file>..." as appropriate to mark resolution)
#       added by them: cepf_sdk/sources/airy_live.py
#       both modified: apps/run_pipeline.py
```

---

## Phase 3: airy_live.py を一括解決

### 3.1 リモート版（新しい実装）を全採用

```bash
# リモート版（マルチスレッド化）を採用
git checkout --theirs cepf_sdk/sources/airy_live.py

# ステージに追加（解決完了）
git add cepf_sdk/sources/airy_live.py

# 確認
git status
# both added: cepf_sdk/sources/airy_live.py ← ✅ green に変わった
```

**なぜ theirs か**:
- リモート版（`73b877b`）: agg_seconds=1.0、マルチスレッド化、パフォーマンス最適化
- ローカル版（HEAD）: 古いシングルスレッド版
- 新しい設計を採用するのが正解

---

## Phase 4: run_pipeline.py を手動解決

### ⚠️ 重要: このファイルは複雑な競合がある

```bash
# コンフリクト箇所を確認
git diff apps/run_pipeline.py > /tmp/conflict_detail.patch
cat /tmp/conflict_detail.patch | head -100
```

### 4.1 エディタで開く

```bash
nano apps/run_pipeline.py
# または
vim apps/run_pipeline.py
```

---

### 4.2 コンフリクト箇所 1-6 を解決

このファイルには **6 つのコンフリクト** があります。以下のパターンで識別できます：

```python
<<<<<<< HEAD (ローカル: 現在のブランチ)
... ローカル版のコード ...
=======
... リモート版のコード ...
>>>>>>> 73b877b (リモート: マージ対象)
```

**以下の手順で 1 つずつ解決** → 各コンフリクト区間を削除して統合版を記述

---

#### **コンフリクト 1: `--use-airy-live` 引数**

**位置**: `main()` 関数の `parser.add_argument()` セクション

**ローカル側にあり、リモート側にない** → ローカルのコードを採用

```python
# ✅ 削除: <<<<<<< HEAD と ======= 以降を全削除
# ✅ 保持: --use-airy-live の parser.add_argument ブロック

parser.add_argument(
    "--use-airy-live",
    action="store_true",
    help="AiryLiveSource を使用してリアルタイムデータを取得",
)
parser.add_argument("--airy-port", type=int, default=6699,
                    help="Airy UDP ポート番号 (default: 6699)")
```

---

#### **コンフリクト 2: `--transform-*` 引数のスペーシング**

**位置**: `--transform-azimuth`, `--transform-elevation` 等

**ローカル側**: スペースが多い
```python
    parser.add_argument("--transform-azimuth",   type=float, default=None,
```

**リモート側**: スペースが少ない
```python
    parser.add_argument("--transform-azimuth", type=float, default=None,
```

**判断**: どちらか一方を統一（リモート側の方が Python PEP8 に合致）

```python
# ✅ 採用: リモート版（スペース少なめ）
parser.add_argument("--transform-azimuth", type=float, default=None,
                    help="Transform: 方位角回転 [deg]")
parser.add_argument("--transform-elevation", type=float, default=None,
                    help="Transform: 仰角回転 [deg]")
parser.add_argument("--transform-tx", type=float, default=None,
                    help="Transform: X 平行移動 [m]")
parser.add_argument("--transform-ty", type=float, default=None,
                    help="Transform: Y 平行移動 [m]")
parser.add_argument("--transform-tz", type=float, default=None,
                    help="Transform: Z 平行移動 [m]")
```

---

#### **コンフリクト 3: sensors.json のエラーメッセージ**

**位置**: `config_path.exists()` のエラー処理

**ローカル側**:
```python
logger.info("sensors.example.json をコピーして sensors.json を作成してください。")
```

**リモート側**:
```python
logger.info("sensors.json を作成してください。")
```

**判断**: ローカル側が詳しい → 採用

```python
logger.error("設定ファイルが見つかりません: %s", config_path)
logger.info("sensors.example.json をコピーして sensors.json を作成してください。")
```

---

#### **コンフリクト 4: フィルタ構築ロジック**

**位置**: `main()` の `# フィルター構築` セクション

**ローカル側**: `_build_pipeline(args)` という関数に抽出済み
```python
pipeline = _build_pipeline(args)
```

**リモート側**: デフォルト CylindricalFilter を直接記述（室内パラメータ）
```python
else:
    pipeline = FilterPipeline(
        filters=[
            CylindricalFilter(
                radius_m=5.0,    # 室内スケール
                z_min_m=-0.1,    # 床面直下
                z_max_m=3.0,     # 天井まで
            ),
        ],
        verbose=args.verbose,
    )
```

**判断**: 両方必要（ローカルの関数にリモートの室内パラメータを反映）

**正しい統合**:
```python
# ローカルの _build_pipeline() 関数内で、
# CylindricalFilter のデフォルト値をリモートの値に変更

# apps/run_pipeline.py の _build_pipeline() 関数を探す（L130 付近）
# 以下の行を見つけて:
filters.append(CylindricalFilter(radius_m=50.0, z_min_m=-2.0, z_max_m=30.0))

# これを以下に変更:
filters.append(CylindricalFilter(
    radius_m=5.0,    # 室内スケール
    z_min_m=-0.1,    # 床面直下
    z_max_m=3.0,     # 天井まで
))
```

---

#### **コンフリクト 5: main() メインループ**

**位置**: `source = _create_source(args)` から `for frame in source.frames()` のセクション

**ローカル側**: `_create_source()` で生成、直接ループ
```python
source = _create_source(args)
for frame in source.frames():
    if args.test_frustum:
        log_frustum_stats(frame)
    # ... 処理 ...
```

**リモート側**: スレッド化（receiver スレッド + frame_queue）
```python
import queue

frame_queue: queue.Queue = queue.Queue(maxsize=10)

def _receiver() -> None:
    source = AiryLiveSource(usc, sensor_id="lidar", port=6699, agg_seconds=1.0)
    for frame in source.frames():
        try:
            frame_queue.put_nowait(frame)
        except queue.Full:
            logger.warning("frame queue full, dropping frame")

threading.Thread(target=_receiver, daemon=True).start()
logger.info("Receiver thread started")

while True:
    try:
        frame = frame_queue.get(timeout=2.0)
    except queue.Empty:
        continue
    if args.test_frustum:
        log_frustum_stats(frame)
    # ... 処理 ...
```

**判断**: リモート版（スレッド化）を採用（パフォーマンス向上）



```python
# ✅ 採用: リモート版の全コード
# ローカルの _create_source() は削除（もう使わない）
# かわりにリモート版のスレッドコードを使用
```

---

#### **コンフリクト 6: process_frame() の実装**

**位置**: `process_frame()` 関数の WebSocket 送信部分

**ローカル側**: シンプル送信のみ
```python
def _process_frame(frame, transport=None, ws_loop=None) -> None:
    """フレームを WebSocket で配信する。"""
    if transport is not None and ws_loop is not None:
        asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)
```

**リモート側**: エラーハンドリング callback 追加
```python
def process_frame(frame, transport=None, ws_loop=None) -> None:
    # ... フレーム統計処理 ...
    if transport is not None and ws_loop is not None:
        future = asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)
        future.add_done_callback(
            lambda f: logger.debug("WS send done, err=%s", f.exception()) 
            if f.exception() else None
        )
```

**判断**: リモート版（エラーハンドリング）を採用

```python
# ✅ 採用: リモート版（done_callback 付き）
def process_frame(frame, transport=None, ws_loop=None) -> None:
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is not None and len(x) > 0:
        r = np.sqrt(np.asarray(x)**2 + np.asarray(y)**2 + np.asarray(z)**2)
        p = np.percentile(r, [5, 25, 50, 75, 95])
        logger.info("frame: points=%d  range min=%.3f p5=%.3f p25=%.3f median=%.3f p75=%.3f p95=%.3f max=%.3f [m]",
                    frame.point_count, float(np.min(r)),
                    p[0], p[1], p[2], p[3], p[4], float(np.max(r)))
    if transport is not None and ws_loop is not None:
        future = asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)
        future.add_done_callback(
            lambda f: logger.debug("WS send done, err=%s", f.exception()) 
            if f.exception() else None
        )
```

---

### 4.3 エディタで解決確認

```bash
# すべてのコンフリクト区間（<<< や === や >>>）が削除されたか確認
grep -n "<<<<<<\|=======\|>>>>>>>" apps/run_pipeline.py

# 出力がなければ OK ✅
```

---

## Phase 5: ステージ & cherry-pick 完了

### 5.1 ファイルをステージに追加

```bash
git add apps/run_pipeline.py

# 確認
git status
# On branch merge/airy-driver-fix
# All conflicts fixed but you are still merging.
```

### 5.2 cherry-pick を完了

```bash
git cherry-pick --continue

# 予想される出力:
# [merge/airy-driver-fix 73b877b] チャンネルデータの開始位置修正
#  4 files changed, 103 insertions(+), 47 deletions(-)
```

**確認**:
```bash
git log --oneline | head -3
# 73b877b チャンネルデータの開始位置修正  ✅ マージ完了
# 1cf49bb Merge PR #2: ...
# ...
```

---

## Phase 6: テスト & 検証

### 6.1 テストを実行

```bash
# RoboSense Airy ドライバテスト
pytest tests/test_parsers/test_robosense_airy.py -v

# 予想結果:
# test_decode_packet PASSED
# test_wrong_length_returns_none PASSED
# ... ✅
```

### 6.2 パイプライン動作確認

```bash
# 簡単な起動確認（PCAP 使用）
python apps/run_pipeline.py --use-pcap --test-frustum | head -50

# 予想:
# INFO: FilterPipeline: 1 フィルター構成
# INFO: [FrustumTest] frame_id=1 ...
```

### 6.3 スタート内容確認

```bash
# 新しいパラメータが使用されているか確認
grep -n "radius_m=5" apps/run_pipeline.py
# 145:                radius_m=5.0,    # 室内スケール
```

---

## Phase 7: マージ完了 & stash 復元

### 7.1 変更を確認

```bash
git diff --stat origin/feature/nodejs-viewer-improvements..HEAD

# 表示:
#  apps/run_pipeline.py                      | 30 ++
#  cepf_sdk/drivers/robosense_airy_driver.py |  2
#  cepf_sdk/sources/airy_live.py             | 70 ++
#  tests/test_parsers/test_robosense_airy.py |  2
```

### 7.2 stash した変更を復元

```bash
git stash pop

# 確認
git status
# modified: docs/config-refactoring-spec.md  ← 元の作業が戻ってきた
# modified: ...
```

### 7.3 ブランチを本体にマージ（オプション）

```bash
# 現在: merge/airy-driver-fix ブランチ
# 本体へ統合（テスト完了後）

git checkout feature/nodejs-viewer-improvements
git merge merge/airy-driver-fix

# または pull request で統合
```

---

## トラブルシューティング

### ❌ コンフリクトに失敗した場合

```bash
# cherry-pick を中止（元の状態に戻す）
git cherry-pick --abort

# ブランチをリセット
git checkout feature/nodejs-viewer-improvements

# stash を復元
git stash pop
```

### ❌ エディタで間違えた場合

```bash
# ファイルをリセット（未ステージ状態に）
git reset apps/run_pipeline.py

# もう一度エディタで開く
nano apps/run_pipeline.py
```

### ❌ git add 後に間違いに気付いた

```bash
# ステージから外す
git reset HEAD apps/run_pipeline.py

# エディタで修正
nano apps/run_pipeline.py

# 再度 add
git add apps/run_pipeline.py
```

---

## 参考コマンド集

```bash
# 現在の cherry-pick 状態を確認
git cherry-pick --status
git status

# コンフリクトの詳細を見る
git diff apps/run_pipeline.py

# stash リスト
git stash list
git stash show -p

# ブランチ一覧
git branch -a

# 特定ファイルの変更内容を確認
git diff HEAD cepf_sdk/drivers/robosense_airy_driver.py
```

---

## 完了チェックリスト

- [ ] `git stash` で未コミット変更を退避
- [ ] `git checkout -b merge/airy-driver-fix` で新ブランチ作成
- [ ] `git cherry-pick 73b877b` で適用開始
- [ ] `cepf_sdk/sources/airy_live.py` を `git checkout --theirs` で解決
- [ ] `apps/run_pipeline.py` を手動で 6 箇所解決
- [ ] `git add` でステージに追加
- [ ] `git cherry-pick --continue` で完了
- [ ] テスト実行（pytest, start.sh）
- [ ] `git stash pop` で元の作業を復元
- [ ] 本体ブランチへマージ（または PR 作成）

---

## 次のステップ

1. **このドキュメントを読む** ← 今ここ 👈
2. **Phase 1-2 を実行** → 準備と cherry-pick 開始
3. **Phase 3 を実行** → airy_live.py を一括解決
4. **Phase 4-7 を実行** → run_pipeline.py を手動解決 & テスト

:::info
**何か困ったら**: このドキュメントのいずれかの步を Claude に提示して、「こここういう状況です。次どうします？」と聞くこと。
:::
