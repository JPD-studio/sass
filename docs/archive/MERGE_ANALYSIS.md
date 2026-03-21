# GitHub コミット マージ分析レポート

**コミット**: 73b877bc1b07134230736d57bc0f6b3972bb93a7  
**ブランチ**: feature/akira-saito (PR #2)  
**コミットメッセージ**: チャンネルデータの開始位置修正  
**作成者**: saito-CE (akira.saito@cubeearth.jp)  
**日時**: 2026-03-19 14:01:39 JST  

---

## 変更概要

**4ファイル変更**: +103 -47 lines

| ファイル | 追加 | 削除 | 種類 | 重要度 |
|---------|------|------|------|--------|
| `apps/run_pipeline.py` | 35 | 5 | 機能/パフォーマンス改善 | ⚠️ **高** |
| `cepf_sdk/drivers/robosense_airy_driver.py` | 4 | 2 | バグ修正 | 🔴 **必須** |
| `cepf_sdk/sources/airy_live.py` | 109 | 39 | リファクタ/パフォーマンス改善 | ⚠️ **高** |
| `tests/test_parsers/test_robosense_airy.py` | 2 | 1 | テスト修正 | 🟡 **中** |

---

## ファイル別詳細分析

### 1️⃣ `cepf_sdk/drivers/robosense_airy_driver.py` 🔴 **必須マージ**

**変更内容**:

```python
# L34: チャンネルデータ開始オフセット修正
- CH_OFF = 3  # 誤った値
+ CH_OFF = 4  # 正しい値

# L48: 仰角テーブル変更
- _DEFAULT_VERT_DEG_96 = tuple(np.linspace(-15.0, 15.0, 96).tolist())
+ _DEFAULT_VERT_DEG_96 = tuple(np.linspace(0.0, 90.0, 96).tolist())
```

**理由**: 
- **バグ修正**: CH_OFF のオフセット値が間違っていた（パケット解析の重大なバグ）
- **仰角テーブル修正**: センサー仕様から外れていた（-15°〜+15° → 0°〜90°）
- これらはセンサーデータの正確な取得に **直接影響する破壊的な問題**

**マージ必須**: ✅ **YES**

---

### 2️⃣ `cepf_sdk/sources/airy_live.py` ⚠️ **高 / マージ推奨**

**変更内容**:

#### A. パラメータ追加・デフォルト値変更
```python
# __init__ シグネチャ変更（後方互換）
def __init__(self, usc, sensor_id, port=6699, 
             agg_seconds=0.1,        # → 1.0 に変更
             host="0.0.0.0",
             socket_timeout=1.0,
    +        recv_workers=4,         # ← 新規
    +        recv_queue_size=2000,   # ← 新規
             ) -> None:
```

#### B. マルチスレッド化
- **従来**: シングルスレッド（順序的に処理）
  ```python
  sock = socket(...)
  sock.bind(...)
  while True:
      data, _ = sock.recvfrom()
      frame = usc.forge(...)
      yield frame
  ```

- **新規**: マルチスレッド (パケット受信 + フレーム生成分離)
  ```python
  _recv_loop():      # スレッド1: パケット受信 → pkt_queue
  _forge_worker():   # スレッド2-5: pkt_queue → frame_queue → 本体
  main loop:         # メインスレッド: frame_queue から消費
  ```

#### C. インポート追加
```python
+ import queue       # マルチスレッド用キュー
+ import threading   # スレッド管理
```

**利点**:
- 🟢 UDP パケット損失削減（受信スレッドが固定的に実行）
- 🟢 フレーム生成ワーカー並列化（複数スレッド×複数フレーム処理）
- 🟢 I/O バウンドなタスク分離によるレイテンシ削減

**影響**:
- API は後方互換（新パラメータはデフォルト値付き）
- ただし内部動作が大きく変わる

**マージ推奨**: ✅ **YES** (ドライバ修正との組み合わせで効果大)

---

### 3️⃣ `apps/run_pipeline.py` ⚠️ **高 / マージ推奨**

**変更内容**:

#### A. CylindricalFilter パラメータ変更
```python
# ❌ 従来（屋外スケール）
CylindricalFilter(radius_m=50.0, z_min_m=-30.0, z_max_m=2.0)

# ✅ 新規（屋内スケール）
CylindricalFilter(
    radius_m=5.0,      # 室内スケール
    z_min_m=-0.1,      # 床面直下
    z_max_m=3.0,       # 天井まで
)
```

**コメント**: 「室内スケール」と注記されているが、**仕様書には未反映**

#### B. AiryLiveSource マルチスレッド化
```python
# ❌ 従来
source = AiryLiveSource(usc, sensor_id="lidar", port=6699, agg_seconds=1.0)
for frame in source.frames():
    ... 処理 ...

# ✅ 新規（スレッドセーフなキュー経由）
frame_queue = queue.Queue(maxsize=10)

def _receiver():
    source = AiryLiveSource(...)
    for frame in source.frames():
        try:
            frame_queue.put_nowait(frame)
        except queue.Full:
            logger.warning("frame queue full, dropping frame")

threading.Thread(target=_receiver, daemon=True).start()

while True:
    try:
        frame = frame_queue.get(timeout=2.0)
    except queue.Empty:
        continue
    # 処理 ...
```

#### C. WebSocket 送信エラーハンドリング改善
```python
# ❌ 従来（エラーを無視）
asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)

# ✅ 新規（コールバックでエラーをキャッチ）
future = asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)
future.add_done_callback(
    lambda f: logger.debug("WS send done, err=%s", f.exception()) 
    if f.exception() else None
)
```

**マージ推奨**: ✅ **YES** (ただし CylindricalFilter 値は検証要)

---

### 4️⃣ `tests/test_parsers/test_robosense_airy.py` 🟡 **中 / マージ必須**

**変更内容**:
```python
# テストパケット生成ヘルパー内で driver の CH_OFF 変更に対応
- off = bs + 3 + ci * 3      # ❌ 古い値
+ off = bs + 4 + ci * 3      # ✅ 新しい値
```

**理由**: driver (1️⃣) の修正と対応させないとテストが失敗する

**マージ必須**: ✅ **YES** (1️⃣とセット)

---

## 🔍 このワークスペースとの適合性

このワークスペースの **現在のコード**:

| ファイル | 状態 | ドキュメント仕様 |
|---------|------|-----------------|
| `cepf_sdk/drivers/robosense_airy_driver.py` | **古い CH_OFF (3)** | §2.2 reference にあり |
| `cepf_sdk/sources/airy_live.py` | **シングルスレッド版** | 未記載 |
| `apps/run_pipeline.py` | **多くの構成変更あり** | §6 に記載予定項目 |
| `tests/test_parsers/test_robosense_airy.py` | **古いテスト** | テスト対応 |

---

## 📋 マージ計画

| 優先度 | ファイル | アクション | 検証項目 |
|--------|---------|-----------|---------|
| 🔴 P0 | `cepf_sdk/drivers/robosense_airy_driver.py` | **即座にマージ** | CH_OFF, 仰角テーブル値確認 |
| 🔴 P0 | `tests/test_parsers/test_robosense_airy.py` | **即座にマージ** | テスト実行確認 |
| ⚠️ P1 | `cepf_sdk/sources/airy_live.py` | **マージ前に仕様確認** | マルチスレッド動作、キューサイズ |
| ⚠️ P1 | `apps/run_pipeline.py` | **他の変更と統合確認後** | CylindricalFilter値, マルチスレッド安全性 |

---

## 📝 仕様書更新が必要な項目

| 項目 | 仕様書セクション | 必要な更新 | 優先度 |
|------|-----------------|----------|--------|
| CH_OFF 値修正 | §2.2 (RoboSense Airy ドライバ) | 値を 3→4 に修正 | 🔴 P0 |
| airy_live.py マルチスレッド化 | §2.3 or 新規 | 新しいアーキテクチャ説明 | ⚠️ P1 |
| agg_seconds デフォルト値 | §5.3 or 実装ステップ | 0.1→1.0 に更新 | 🟡 P2 |
| CylindricalFilter 室内パラメータ | §7.3 (実装順序) | 値の根拠・選択肢を記載 | 🟡 P2 |

---

## 結論

### 🟢 **マージ対象ファイル**

```
✅ cepf_sdk/drivers/robosense_airy_driver.py     (バグ修正)
✅ tests/test_parsers/test_robosense_airy.py     (テスト修正)
✅ cepf_sdk/sources/airy_live.py                 (パフォーマンス改善)
✅ apps/run_pipeline.py                          (機能改善)
```

### 🎯 **推奨マージ順序**

1. **Phase A** (必須・即座): 
   - `cepf_sdk/drivers/robosense_airy_driver.py`
   - `tests/test_parsers/test_robosense_airy.py`
   - テスト実行 `pytest tests/test_parsers/test_robosense_airy.py`

2. **Phase B** (推奨・検証後):
   - `cepf_sdk/sources/airy_live.py`
   - 統合テスト実行

3. **Phase C** (慎重・検証後):
   - `apps/run_pipeline.py`
   - CylindricalFilter パラメータ値の根拠確認

### 📌 **注意点**

- これらの変更は **RoboSense Airy センサー専用**
- マルチスレッド導入により**スレッド安全性確保が必須**
- 既存の config/仕様書は **更新が必要**
