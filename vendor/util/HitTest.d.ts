export default class HitTest {
    /**
     * 多角形の最大値、最小値の取得
     * @param paths 多角形のパス
     * @returns 多角形の最大値、最小値
     */
    static getBounds(paths: number[][]): {
        minX: number;
        maxX: number;
        minY: number;
        maxY: number;
    };
    /**
     * 四角形の内在判定
     * @param left
     * @param right
     * @param bottom
     * @param top
     * @param x
     * @param y
     * @returns
     */
    static pointRect(x: number, y: number, left: number, right: number, bottom: number, top: number): boolean;
    /**
     * 多角形上の内在判定
     * @param paths
     * @param y
     * @param x
     * @returns
     */
    static pointPoly(paths: number[][], y: number, x: number): boolean;
    /**
     * 多角形と四角形の当たり判定
     * @param paths
     * @param left
     * @param right
     * @param bottom
     * @param top
     */
    static rectPoly(paths: number[][], left: number, right: number, bottom: number, top: number): boolean;
    /**
     * 線分・線分の当たり判定
     * @param aX
     * @param aY
     * @param bX
     * @param bY
     * @param cX
     * @param cY
     * @param dX
     * @param dY
     * @returns
     */
    static segSeg(aX: number, aY: number, bX: number, bY: number, cX: number, cY: number, dX: number, dY: number): boolean;
    /**
     * 四角形と線分の当たり判定
     * @param aX
     * @param aY
     * @param bX
     * @param bY
     * @param minX
     * @param minY
     * @param maxX
     * @param maxY
     * @returns
     */
    static segRect(aX: number, aY: number, bX: number, bY: number, minX: number, minY: number, maxX: number, maxY: number): boolean;
    /**
     * 四角形、四角形の当たり判定
     * @param left1
     * @param right1
     * @param bottom1
     * @param top1
     * @param left2
     * @param right2
     * @param bottom2
     * @param top2
     * @returns
     */
    static rectRect(left1: number, right1: number, bottom1: number, top1: number, left2: number, right2: number, bottom2: number, top2: number): boolean;
}
