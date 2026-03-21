import * as Cesium from "cesium";

/**
 * PointCloudLayer
 * CesiumJS の PointPrimitiveCollection を管理し、
 * 毎フレームの点群データをリアルタイムで更新する。
 */
export class PointCloudLayer {
  private readonly _collection: Cesium.PointPrimitiveCollection;
  private _pointCount = 0;

  constructor(scene: Cesium.Scene) {
    this._collection = scene.primitives.add(
      new Cesium.PointPrimitiveCollection({
        blendOption: Cesium.BlendOption.TRANSLUCENT,
      })
    );
  }

  /**
   * 点群を WGS84 座標で一括更新（毎フレーム呼び出し）
   * removeAll() + add() で全点を置き換える。
   */
  update(points: { lat: number; lng: number; alt: number }[]): void {
    this._collection.removeAll();
    for (const p of points) {
      this._collection.add({
        position: Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt),
        pixelSize: 3,
        color: Cesium.Color.YELLOW,
      });
    }
    this._pointCount = points.length;
  }

  get pointCount(): number {
    return this._pointCount;
  }
}
