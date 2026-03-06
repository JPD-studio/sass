"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
var HitTest = /** @class */ (function () {
    function HitTest() {
    }
    /**
     * 多角形の最大値、最小値の取得
     * @param paths 多角形のパス
     * @returns 多角形の最大値、最小値
     */
    HitTest.getBounds = function (paths) {
        var maxX = Number.MIN_VALUE, maxY = Number.MIN_VALUE, minX = Number.MAX_VALUE, minY = Number.MAX_VALUE;
        for (var i = 0; i < paths.length; i++) {
            var x = paths[i][1]; // lng
            var y = paths[i][0]; // lat
            if (x > maxX)
                maxX = x;
            if (y > maxY)
                maxY = y;
            if (x < minX)
                minX = x;
            if (y < minY)
                minY = y;
        }
        return { minX: minX, maxX: maxX, minY: minY, maxY: maxY };
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
    HitTest.pointRect = function (x, y, left, right, bottom, top) {
        return ((bottom < y && y < top) && (left < x && x < right));
    };
    /**
     * 多角形上の内在判定
     * @param paths
     * @param y
     * @param x
     * @returns
     */
    HitTest.pointPoly = function (paths, y, x) {
        var cn = 0;
        for (var i = 0, j = paths.length - 1; i < paths.length; j = i++) {
            // 多角形を成す辺を全て調査する
            // 現在の index の多角形の点X, Y
            var polCX = paths[i][1];
            var polCY = paths[i][0];
            // 次の index の多角形の点X, Y
            var polNX = paths[j][1];
            var polNY = paths[j][0];
            if (polCY > y === polNY > y) {
                // 点が辺の完全に上 or 完全に下ならば. ノーカウントでループ続行
                continue;
            }
            // 辺が点pと同じ高さになる位置を特定し、その時のxの値と点pのxの値を比較する
            // 同じ高さになる時の辺の割合 = (点Y - 始点Y座標)) / 辺のY軸長さ
            var vt = (y - polCY) / (polNY - polCY);
            // 点のX座標 < 辺のX軸長さ * 同じ高さになる時の辺の割合 + 始点X座標
            if (x < (polNX - polCX) * vt + polCX) {
                cn++;
            }
        }
        return cn % 2 === 1;
    };
    /**
     * 多角形と四角形の当たり判定
     * @param paths
     * @param left
     * @param right
     * @param bottom
     * @param top
     */
    HitTest.rectPoly = function (paths, left, right, bottom, top) {
        var work = NaN;
        if (left > right) {
            work = left;
            left = right;
            right = work;
        }
        if (bottom > top) {
            work = bottom;
            bottom = top;
            top = work;
        }
        // for (let i = 0; i < paths.length - 1; i++) {
        //   const e = paths[i];
        if (this.pointPoly(paths, bottom, left))
            return true;
        if (this.pointPoly(paths, top, left))
            return true;
        if (this.pointPoly(paths, bottom, right))
            return true;
        if (this.pointPoly(paths, top, right))
            return true;
        //}
        return false;
    };
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
    HitTest.segSeg = function (aX, aY, bX, bY, cX, cY, dX, dY) {
        var dB = +(bX - aX) * (dY - cY) - (bY - aY) * (dX - cX);
        if (0 === dB)
            return false; // 平行
        var acX = +cX - aX;
        var acY = +cY - aY;
        var dR = +((dY - cY) * acX - (dX - cX) * acY) / dB;
        var dS = +((bY - aY) * acX - (bX - aX) * acY) / dB;
        return (0 < dR && dR < 1) && (0 < dS && dS < 1);
    };
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
    HitTest.segRect = function (aX, aY, bX, bY, minX, minY, maxX, maxY) {
        if (HitTest.rectRect(aX, bX, aY, bY, minX, maxX, minY, maxY)) {
            if (HitTest.segSeg(aX, aY, bX, bY, minX, minY, minX, maxY)) {
                return true;
            }
            if (HitTest.segSeg(aX, aY, bX, bY, minX, maxY, maxX, maxY)) {
                return true;
            }
            if (HitTest.segSeg(aX, aY, bX, bY, maxX, maxY, maxX, minY)) {
                return true;
            }
            if (HitTest.segSeg(aX, aY, bX, bY, maxX, minY, minX, minY)) {
                return true;
            }
        }
        return false;
    };
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
    HitTest.rectRect = function (left1, right1, bottom1, top1, left2, right2, bottom2, top2) {
        var center1X = (left1 + right1) / 2.0;
        var center2X = (left2 + right2) / 2.0;
        var center1Y = (bottom1 + top1) / 2.0;
        var center2Y = (bottom2 + top2) / 2.0;
        var width1 = Math.abs(right1 - left1);
        var width2 = Math.abs(right2 - left2);
        var height1 = Math.abs(top1 - bottom1);
        var height2 = Math.abs(top2 - bottom2);
        return (Math.abs(center1X - center2X) < width1 / 2 + width2 / 2 // 横の判定
            &&
                Math.abs(center1Y - center2Y) < height1 / 2 + height2 / 2 // 縦の判定
        );
    };
    return HitTest;
}());
exports.default = HitTest;
