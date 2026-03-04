# Vendor フォルダ

共有ユーティリティとモデル定義を管理するライブラリフォルダです。複数のプロジェクト間で使用される共通機能が集約されています。

## フォルダ構成

### 📍 `models/`
地理座標グリッドシステムの型定義とモデル

- **IGrid** — 2次元グリッドの境界（北/南/東/西）と単位を定義
- **IGrid3D** — 3次元グリッドの境界に高度範囲を追加した定義
- **ILatLng** — 緯度・経度インターフェース
- **LatLng.js** — 座標の成生成・変換メソッド

### 🔧 `util/`
一般的なユーティリティクラス

- **Util** — 文字列パディング、数値丸め（小数第6位）、乱数生成など
- **HitTest** — 当たり判定・交差判定ロジック

### 🔐 `alogs/` 
グリッドID と地理座標の相互変換（エンコード・デコード）

- **Decode** — グリッドID から 緯度経度/3D位置情報への変換
- **Encode** — 緯度経度 から グリッドID への変換
- **CEex** — カスタムエンコーディング処理（最小化版）

## 使用例

```typescript
import Decode from './vendor/alogs/Decode';
import { Util } from './vendor/util/Util';

// グリッドIDを地理座標に変換
const gridInfo = Decode.gridIdToLatlng("ABC123");

// 数値を丸める
const rounded = Util.round6(3.141592653);
```
---

## サンプル地点（明石市立天文科学館周辺）

| ID | 地点 | 緯度（十進度） | 経度（十進度） | 標高 (m) | 備考 |
|----|------|-------------|-------------|---------|------|
| 1 | 塔時計（子午線標示） | 34.649472 | 135.000000 | 108 | 標高54m ＋ 塔高約54m |
| 2 | 子午線標（屋外） | 34.650861 | 135.000000 |  53 | 科学館北側の道路沿い |
| 3 | 科学館 1階 | 34.649389 | 134.999861 |  54 | 建物1階フロア |
| 4 | 科学館 2階 | 34.649389 | 134.999861 |  60 | 建物2階フロア |
| 5 | 科学館 屋上 | 34.649389 | 134.999861 |  70 | 建物屋上 |

> **度分秒 → 十進度の変換式:** `十進度 = 度 + 分/60 + 秒/3600`  
> 例: 34° 38' 58.1" = 34 + 38/60 + 58.1/3600 = **34.649472**

---

## API リファレンス

### `alogs/Encode`

緯度経度をグリッドIDに変換するクラス。

---

#### `Encode.LatLngToID(lat, lng, gridUnit?): string`

緯度・経度を **2D グリッドID** に変換する。

| 引数 | 型 | 省略可 | 説明 |
|------|----|--------|------|
| `lat` | `number` | 不可 | 緯度（十進度） |
| `lng` | `number` | 不可 | 経度（十進度） |
| `gridUnit` | `number` | 可（デフォルト: `1`） | グリッドサイズ（メートル） |

**戻り値:** グリッドID文字列。対象外の座標の場合は空文字列 `""`。

```typescript
import Encode from './vendor/alogs/Encode';

// (1) 塔時計（子午線 1mグリッド）
const id1 = Encode.LatLngToID(34.649472, 135.000000);
// → グリッドID（例: "ABC123..."）

// (3) 科学館1階（10mグリッド）
const id3 = Encode.LatLngToID(34.649389, 134.999861, 10);

// (2) 子午線標（屋外）
const id2 = Encode.LatLngToID(34.650861, 135.000000);
```

---

#### `Encode.LatLngTo3DID(lat, lng, alt, unit?): string`

緯度・経度・高さを **3D グリッドID** に変換する。

| 引数 | 型 | 省略可 | 説明 |
|------|----|--------|------|
| `lat` | `number` | 不可 | 緯度（十進度） |
| `lng` | `number` | 不可 | 経度（十進度） |
| `alt` | `number` | 不可 | 高度（メートル） |
| `unit` | `number` | 可（デフォルト: `1`） | グリッドサイズ（メートル） |

**戻り値:** 3D グリッドID文字列。

```typescript
import Encode from './vendor/alogs/Encode';

// (1) 塔時計（標高108m）
const id3d_1 = Encode.LatLngTo3DID(34.649472, 135.000000, 108);

// (4) 科学館2階（標高60m）
const id3d_4 = Encode.LatLngTo3DID(34.649389, 134.999861, 60);

// (5) 科学館屋上（標高70m）
const id3d_5 = Encode.LatLngTo3DID(34.649389, 134.999861, 70);
```

---

#### `Encode.GridLine(lat, lng, unit?, numOfLine?): string`

指定位置の周辺グリッドライン（緯度・経度の境界）を取得する。

| 引数 | 型 | 省略可 | 説明 |
|------|----|--------|------|
| `lat` | `number` | 不可 | 緯度 |
| `lng` | `number` | 不可 | 経度 |
| `unit` | `number` | 可（デフォルト: `1`） | グリッド単位（メートル） |
| `numOfLine` | `number` | 可（デフォルト: `200`, 最大: `1000`） | 取得するライン数 |

**戻り値:** グリッド線リスト（オブジェクト形式の文字列）。

```typescript
import Encode from './vendor/alogs/Encode';

// 科学館1階周辺の5mグリッドのグリッドラインを100本取得
const lines = Encode.GridLine(34.649389, 134.999861, 5, 100);
```

---

#### `Encode.GridLine3D(lat, lng, alt, unit?, numOfLine?): string`

指定位置の周辺の **3Dグリッドライン** を取得する。

| 引数 | 型 | 省略可 | 説明 |
|------|----|--------|------|
| `lat` | `number` | 不可 | 緯度 |
| `lng` | `number` | 不可 | 経度 |
| `alt` | `number` | 不可 | 高度（メートル） |
| `unit` | `number` | 可 | グリッド単位（メートル） |
| `numOfLine` | `number` | 可 | 取得するライン数 |

```typescript
import Encode from './vendor/alogs/Encode';

// 塔時計周辺の3Dグリッドライン（1mグリッド）
const lines3d = Encode.GridLine3D(34.649472, 135.000000, 108, 1, 50);
```

---

### `alogs/Decode`

グリッドIDを緯度経度（グリッド境界情報）に変換するクラス。

---

#### `Decode.gridIdToLatlng(address): IGrid`

グリッドIDを **2Dグリッド情報**（境界ボックス）に変換する。

| 引数 | 型 | 説明 |
|------|----|------|
| `address` | `string` | グリッドID |

**戻り値:** `IGrid`

```typescript
interface IGrid {
  bounds: {
    north: number;  // 北端の緯度
    south: number;  // 南端の緯度（= そのグリッドの南西下の緯度）
    east:  number;  // 東端の経度
    west:  number;  // 西端の経度（= そのグリッドの南西下の経度）
  };
  unit: number;     // グリッド単位（メートル）
}
```

```typescript
import Encode from './vendor/alogs/Encode';
import Decode from './vendor/alogs/Decode';

// (1) 塔時計のグリッドIDを取得し、南西端（南西下の緯経度）を求める
const gridId = Encode.LatLngToID(34.649472, 135.000000);
const grid   = Decode.gridIdToLatlng(gridId);

console.log(grid.bounds.south); // 南端の緯度（南西下の緯度）
console.log(grid.bounds.west);  // 西端の経度（南西下の経度）
console.log(grid.bounds.north); // 北端の緯度
console.log(grid.bounds.east);  // 東端の経度
console.log(grid.unit);         // グリッドサイズ（m）
```

---

#### `Decode.gridIdTo3DLocation(address): IGrid3D`

グリッドIDを **3Dグリッド情報**（境界ボックス ＋ 高度範囲）に変換する。

| 引数 | 型 | 説明 |
|------|----|------|
| `address` | `string` | 3D グリッドID |

**戻り値:** `IGrid3D`

```typescript
interface IGrid3D {
  bounds: {
    north: number;  // 北端の緯度
    south: number;  // 南端の緯度
    east:  number;  // 東端の経度
    west:  number;  // 西端の経度
  };
  altitude: {
    upper: number;  // グリッドの上端高度（m）
    lower: number;  // グリッドの下端高度（m）= 南西下の高さ
  };
  unit: number;     // グリッド単位（メートル）
}
```

```typescript
import Encode from './vendor/alogs/Encode';
import Decode from './vendor/alogs/Decode';

// (5) 科学館屋上の3DグリッドIDを取得し、ボクセルの南西下の全座標を求める
const gridId3d  = Encode.LatLngTo3DID(34.649389, 134.999861, 70);
const grid3d    = Decode.gridIdTo3DLocation(gridId3d);

const southWestBottom = {
  lat: grid3d.bounds.south,    // 南端の緯度
  lng: grid3d.bounds.west,     // 西端の経度
  alt: grid3d.altitude.lower,  // 下端の高度（m）
};
console.log(southWestBottom);
// → { lat: 34.649389, lng: 134.999861, alt: 70.0 } (グリッド境界値)

// 科学館の2階〜屋上の高度差を確認
const id_floor2 = Encode.LatLngTo3DID(34.649389, 134.999861, 60);
const id_roof   = Encode.LatLngTo3DID(34.649389, 134.999861, 70);
const g_floor2  = Decode.gridIdTo3DLocation(id_floor2);
const g_roof    = Decode.gridIdTo3DLocation(id_roof);
console.log(g_floor2.altitude); // { lower: 60, upper: 61 }
console.log(g_roof.altitude);   // { lower: 70, upper: 71 }
```

---

### `util/Util`

汎用ユーティリティクラス。

---

#### `Util.round6(num): number`

数値を **小数第6位** で四捨五入する。

```typescript
import { Util } from './vendor/util/Util';

Util.round6(34.6494722222);  // → 34.649472
Util.round6(134.9998611111); // → 134.999861
```

---

#### `Util.paddingleft(val, char, length): string`

文字列を指定文字で **左パディング** する。

| 引数 | 型 | 説明 |
|------|----|------|
| `val` | `string` | パディング対象の文字列 |
| `char` | `string` | パディングに使う文字 |
| `length` | `number` | 結果の文字列長 |

```typescript
import { Util } from './vendor/util/Util';

Util.paddingleft('42', '0', 6);  // → "000042"
Util.paddingleft('abc', ' ', 8); // → "     abc"
```

---

#### `Util.getRandomInt(max): number`

`0` 以上 `max` 未満のランダムな整数を返す。

```typescript
import { Util } from './vendor/util/Util';

Util.getRandomInt(5); // → 0, 1, 2, 3, 4 のいずれか
```

---

#### `Util.now(): number`

現在時刻をミリ秒単位のタイムスタンプで返す。

```typescript
import { Util } from './vendor/util/Util';

const ts = Util.now(); // → 例: 1741132800000
```

---

### `util/HitTest`

当たり判定クラス。2D座標の点・線・多角形・矩形の交差判定を提供する。

> **座標軸について:** 緯度方向を Y 軸、経度方向を X 軸として使用する。

---

#### `HitTest.pointRect(x, y, left, right, bottom, top): boolean`

**点が矩形の内側にあるか**を判定する。

```typescript
import HitTest from './vendor/util/HitTest';

// 科学館1階 (3) が 塔時計(1)〜子午線標(2) の矩形範囲内にあるか
const inRect = HitTest.pointRect(
  134.999861,  // x = 科学館の経度
  34.649389,   // y = 科学館の緯度
  134.999861,  // left  （西端）
  135.000000,  // right （東端）
  34.649389,   // bottom（南端）
  34.650861    // top   （北端）
);
// → true
```

---

#### `HitTest.pointPoly(paths, y, x): boolean`

**点が多角形の内側にあるか**を判定する。

| 引数 | 型 | 説明 |
|------|----|------|
| `paths` | `number[][]` | 多角形の頂点リスト `[[x,y], [x,y], ...]` |
| `y` | `number` | 判定したい点の Y 座標（緯度） |
| `x` | `number` | 判定したい点の X 座標（経度） |

```typescript
import HitTest from './vendor/util/HitTest';

// 塔時計(1)・子午線標(2)・科学館(3) を頂点とする三角形に
// 科学館1階(3)が含まれるか判定
const polygon = [
  [135.000000, 34.649472], // (1) 塔時計
  [135.000000, 34.650861], // (2) 子午線標
  [134.999861, 34.649389], // (3) 科学館
];
const inside = HitTest.pointPoly(polygon, 34.649389, 134.999861);
// → true
```

---

#### `HitTest.rectPoly(paths, left, right, bottom, top): boolean`

**多角形と矩形が交差・重なっているか**を判定する。

```typescript
import HitTest from './vendor/util/HitTest';

const polygon = [
  [135.000000, 34.649472],
  [135.000000, 34.650861],
  [134.999861, 34.649389],
];
const hit = HitTest.rectPoly(polygon, 134.999, 135.001, 34.648, 34.651);
// → true
```

---

#### `HitTest.segSeg(aX, aY, bX, bY, cX, cY, dX, dY): boolean`

**2本の線分が交差するか**を判定する。

```typescript
import HitTest from './vendor/util/HitTest';

// 線分: 塔時計(1) → 科学館(3)  と  子午線標(2) → 科学館(3) が交差するか
const cross = HitTest.segSeg(
  135.000000, 34.649472,  // A: 塔時計
  134.999861, 34.649389,  // B: 科学館
  135.000000, 34.650861,  // C: 子午線標
  134.999861, 34.649389   // D: 科学館
);
```

---

#### `HitTest.segRect(aX, aY, bX, bY, minX, minY, maxX, maxY): boolean`

**線分と矩形が交差するか**を判定する。

```typescript
import HitTest from './vendor/util/HitTest';

const hit = HitTest.segRect(
  135.000000, 34.649472,  // 線分の端点A（塔時計）
  134.999861, 34.649389,  // 線分の端点B（科学館）
  134.9995, 34.649,       // 矩形の min
  135.0005, 34.651        // 矩形の max
);
// → true
```

---

#### `HitTest.rectRect(left1, right1, bottom1, top1, left2, right2, bottom2, top2): boolean`

**2つの矩形が重なっているか**を判定する。

```typescript
import HitTest from './vendor/util/HitTest';

// 塔時計(1)と子午線標(2) を含む矩形 と 科学館エリアの矩形 が重なるか
const overlap = HitTest.rectRect(
  134.9998, 135.0001, 34.649, 34.651, // 矩形1
  134.9995, 135.0000, 34.648, 34.650  // 矩形2
);
// → true
```

---

#### `HitTest.getBounds(paths): { minX, maxX, minY, maxY }`

多角形の **バウンディングボックス**（最大・最小値）を取得する。

```typescript
import HitTest from './vendor/util/HitTest';

const polygon = [
  [135.000000, 34.649472], // (1) 塔時計
  [135.000000, 34.650861], // (2) 子午線標
  [134.999861, 34.649389], // (3) 科学館
];
const bounds = HitTest.getBounds(polygon);
// → { minX: 134.999861, maxX: 135.0, minY: 34.649389, maxY: 34.650861 }
```

---

### `models/LatLng`

緯度・経度を保持するモデルクラス。

```typescript
import LatLng from './vendor/models/LatLng';

// 配列で初期化
const p1 = new LatLng([34.649472, 135.000000]); // (1) 塔時計

// 個別値で初期化
const p2 = new LatLng(34.650861, 135.000000);   // (2) 子午線標

console.log(p1.lat); // → 34.649472
console.log(p1.lng); // → 135.0

// setter
p1.lat = 34.649389; // (3) 科学館の緯度に変更
```