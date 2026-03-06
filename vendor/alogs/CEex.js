"use strict";
var __extends = (this && this.__extends) || (function () {
    var extendStatics = function (d, b) {
        extendStatics = Object.setPrototypeOf ||
            ({ __proto__: [] } instanceof Array && function (d, b) { d.__proto__ = b; }) ||
            function (d, b) { for (var p in b) if (Object.prototype.hasOwnProperty.call(b, p)) d[p] = b[p]; };
        return extendStatics(d, b);
    };
    return function (d, b) {
        if (typeof b !== "function" && b !== null)
            throw new TypeError("Class extends value " + String(b) + " is not a constructor or null");
        extendStatics(d, b);
        function __() { this.constructor = d; }
        d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
var LatLng_1 = require("../models/LatLng");
var HitTest_1 = require("../util/HitTest");
var Decode_1 = require("./Decode");
var Encode_1 = require("./Encode");
var CEex = /** @class */ (function (_super) {
    __extends(CEex, _super);
    function CEex() {
        return _super !== null && _super.apply(this, arguments) || this;
    }
    /**
     * 2点で指定される矩形の範囲のGridIDの一覧を取得
     * @param latLng1
     * @param latLng2
     * @returns 2点で指定される矩形の範囲のGridIDの一覧
     */
    CEex.getAreaIDs = function (latLng1, latLng2, unit) {
        var ret = [];
        var maxLat = Math.max(latLng1.lat, latLng2.lat);
        var minLat = Math.min(latLng1.lat, latLng2.lat);
        var maxLng = Math.max(latLng1.lng, latLng2.lng);
        var minLng = Math.min(latLng1.lng, latLng2.lng);
        var lat = minLat, lng = minLng;
        // 最小値のBasisを取得
        var basis = CEex.getBasis({ lat: lat, lng: lng });
        var list = CEex.getGridID(basis);
        // unitが500m各の場合
        if (this.ONE_UNIT_GRID == unit) {
            var gridLng = 0;
            var gridLat = 0;
            while (lat - gridLat <= maxLat) {
                lng = minLng;
                while (lng - gridLng <= maxLng) {
                    // let gridLng = CEex.getPitchLngFromLatLng(new LatLng(lat, lng));
                    var latIndex = CEex.binarySearch1(list.lat, lat);
                    var lngIndex = CEex.binarySearch1(list.lng, lng);
                    //Indexがない場合は新しいgridListを引っ張ってくる。
                    if (latIndex < 0 || lngIndex < 0) {
                        var basis_1 = CEex.getBasis({ lat: lat, lng: lng });
                        list = CEex.getGridID(basis_1);
                        latIndex = CEex.binarySearch1(list.lat, lat);
                        lngIndex = CEex.binarySearch1(list.lng, lng);
                    }
                    var gridId = CEex.LatLngToID(list.lat[latIndex], list.lng[lngIndex], unit);
                    gridLat = list.gridLat;
                    gridLng = list.gridLng;
                    ret.push({ id: gridId, grid: Decode_1.default.gridIdToLatlng(gridId) });
                    if (ret.length > 1024 * 20) { // ブロック数が1024 * 20を限度とする
                        return ret;
                    }
                    lng += gridLng;
                }
                lat += gridLat;
            }
            return ret;
        }
        else {
            // unitの指定がある場合
            var gridLng = 0;
            var gridLat = 0;
            while (lat - gridLat <= maxLat) {
                lng = minLng;
                while (lng - gridLng <= maxLng) {
                    // 500mピッチのGridLng
                    var latIndex = CEex.binarySearch1(list.lat, lat);
                    var lngIndex = CEex.binarySearch1(list.lng, lng);
                    //Indexがない場合は新しいListを引っ張ってくる。
                    if (latIndex < 0 || lngIndex < 0) {
                        var basis_2 = CEex.getBasis({ lat: lat, lng: lng });
                        list = CEex.getGridID(basis_2);
                        latIndex = CEex.binarySearch1(list.lat, lat);
                        lngIndex = CEex.binarySearch1(list.lng, lng);
                    }
                    // 指定ピッチのListとIndexの取得
                    // 分割したListとIndexを取得
                    var _a = CEex.getSplitIndex(list, latIndex, lngIndex, lat, lng, unit), splitLatIndex = _a.splitLatIndex, splitLngIndex = _a.splitLngIndex, splitList = _a.splitList;
                    var gridId = JSON.parse(CEex.getAddress(splitLatIndex, splitLngIndex, splitList, unit));
                    gridLng = splitList.gridLng;
                    gridLat = splitList.gridLat;
                    // const gridId = CEex.LatLngToID(list.lat[latIndex], list.lng[lngIndex], unit);
                    ret.push(gridId);
                    // if (ret.length > 1024) { // ブロック数が1024を限度とする
                    //   return ret;
                    // }
                    lng += gridLng; // 経度を追加
                }
                lat += gridLat; // 緯度を追加;
            }
        }
        return ret;
    };
    /**
     * 多角形中に含まれるの空間IDの取得
     * @param polygon 多角形
     * @param unit 単位長さ
     * @returns 多角形中に含まれるの空間ID
     */
    CEex.getContainPoygonIDs = function (polygon, unit) {
        // 多角形が作れない場合は、エラーを返す
        if (polygon.length < 3) {
            return [{ id: "", grid: { bounds: { north: NaN, south: NaN, east: NaN, west: NaN }, unit: unit } }];
        }
        var p = JSON.parse(JSON.stringify(polygon));
        var start = p[0];
        var end = p[p.length - 1];
        // 閉じたPolygon出ない場合、閉じる
        if (!(start.lat !== end.lat && start.lng !== end.lng)) {
            p.push(p[0]);
        }
        var lats = polygon.map(function (a) { return a.lat; });
        var lngs = polygon.map(function (a) { return a.lng; });
        var north = lats.reduce(function (a, b) { return Math.max(a, b); });
        var south = lats.reduce(function (a, b) { return Math.min(a, b); });
        var east = lngs.reduce(function (a, b) { return Math.max(a, b); });
        var west = lngs.reduce(function (a, b) { return Math.min(a, b); });
        var ids = CEex.getAreaIDs(new LatLng_1.default([north, east]), new LatLng_1.default([south, west]), unit);
        var ret = new Array();
        var path = polygon.map(function (a) { return [a.lat, a.lng]; });
        for (var i = 0; i < ids.length; i++) {
            var bounds = ids[i].grid.bounds;
            if (HitTest_1.default.rectPoly(path, bounds.west, bounds.east, bounds.south, bounds.north)) {
                ret.push(ids[i]);
            }
        }
        return ret;
    };
    /**
   * 線に接触するの空間IDの取得
   * @param line 線
   * @param unit 単位長さ
   * @returns 多角形中に含まれるの空間ID
   */
    CEex.getHitLineIDs = function (line, unit) {
        // 線が作れない場合は、エラーを返す
        if (line.length < 2) {
            return [{ id: "", grid: { bounds: { north: NaN, south: NaN, east: NaN, west: NaN }, unit: unit } }];
        }
        var lats = line.map(function (a) { return a.lat; });
        var lngs = line.map(function (a) { return a.lng; });
        var north = lats.reduce(function (a, b) { return Math.max(a, b); });
        var south = lats.reduce(function (a, b) { return Math.min(a, b); });
        var east = lngs.reduce(function (a, b) { return Math.max(a, b); });
        var west = lngs.reduce(function (a, b) { return Math.min(a, b); });
        var ids = CEex.getAreaIDs(new LatLng_1.default([north, east]), new LatLng_1.default([south, west]), unit);
        var ret = new Set();
        var path = line.map(function (a) { return [a.lat, a.lng]; });
        for (var i = 0; i < ids.length; i++) {
            var bounds = ids[i].grid.bounds;
            for (var j = 0; j < path.length - 1; j++) {
                var e1 = path[j];
                var e2 = path[j + 1];
                if (HitTest_1.default.segRect(e1[1], e1[0], e2[1], e2[0], bounds.west, bounds.south, bounds.east, bounds.north)) {
                    ret.add(ids[i]);
                }
            }
        }
        return Array.from(ret);
    };
    /**
     * 特定の座標を基準にして、指定したブロック数のGridIDを取得
     * @param latlng 基準座標
     * @param alt 高度
     * @param unit 単位長さ
     * @param numOf 周辺ブロック数
     * @return 指定したブロック一覧
     */
    CEex.getGrid3IDs = function (latlng, alt, unit, numOf) {
        if (unit <= 0) {
            throw new Error('unitは0より大きい値を指定してください。');
        }
        var ret = [];
        var basisId = CEex.getBasis(latlng);
        var oneUnitAlts = Encode_1.default.getDivAltitude(unit);
        var list = CEex.getGridID(basisId);
        // 周辺ブロック数を指定して、周辺のブロックを取得
        for (var i = -numOf; i < numOf; i++) {
            for (var j = -numOf; j < numOf; j++) {
                for (var k = 0; k < numOf * 2; k++) {
                    // 基準座標からのオフセットを計算
                    var latIndex = CEex.binarySearch1(list.lat, latlng.lat + i * list.gridLat);
                    var lngIndex = CEex.binarySearch1(list.lng, latlng.lng + j * list.gridLng);
                    var altIndex = CEex.binarySearch1(oneUnitAlts, alt + k * unit);
                    // Indexがない場合は、MaxIndexから引っ張る必要があるが日本で使うのでとりあえず　考慮しない
                    if (latIndex >= 0 && lngIndex >= 0 && altIndex >= 0) {
                        // ここが重いのでキャッシュを作りながら実装する。
                        var gridId = '';
                        if (this.ONE_UNIT_GRID == unit) {
                            //const aIndex = Encode.binarySearch1(oneUnitAlts, alt)
                            gridId = Encode_1.default.getAddress3D(latIndex, lngIndex, altIndex, list, oneUnitAlts, unit);
                        }
                        else {
                            var lat = list.lat[latIndex], lng = list.lng[lngIndex];
                            var _a = Encode_1.default.getSplitIndex(list, latIndex, lngIndex, lat, lng, unit), splitLatIndex = _a.splitLatIndex, splitLngIndex = _a.splitLngIndex, splitList = _a.splitList;
                            //const aIndex = Encode.binarySearch1(oneUnitAlts, alt);
                            gridId = Encode_1.default.getAddress3D(splitLatIndex, splitLngIndex, altIndex, splitList, oneUnitAlts, unit);
                        }
                        //const gridId = CEex.LatLngTo3DID(list.lat[latIndex], list.lng[lngIndex], oneUnitAlts[altIndex], unit);
                        var grid = JSON.parse(gridId);
                        ret.push(grid);
                    }
                }
            }
        }
        var center = JSON.parse(CEex.LatLngTo3DID(latlng.lat, latlng.lng, alt, unit));
        var retAdd = { center: center, elements: ret };
        console.log('length:', ret.length);
        return retAdd;
    };
    return CEex;
}(Encode_1.default));
exports.default = CEex;
