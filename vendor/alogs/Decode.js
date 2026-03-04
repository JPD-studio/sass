"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
var Util_1 = require("../util/Util");
var Encode_1 = require("./Encode");
var Decode = /** @class */ (function () {
    function Decode() {
    }
    ////////////////////////
    // GridAddressからGridInfoをデコード
    Decode.gridIdToLatlng = function (address) {
        var info = { lat: 0, gridLat: 0, lng: 0, gridLng: 0 };
        var arr = '';
        // Addressを数値に変換->２進数に変換
        try {
            for (var i = 0; i < address.length; i++) {
                var str = address[i];
                arr += Util_1.Util.paddingleft(parseInt(this.base64Dec[str].toString()).toString(2), '0', 6);
            }
        }
        catch (err) {
            console.error(err.message);
        }
        // 先頭ビットが1の場合は、マイナス値なので補数を取る
        if (arr.substring(0, 32)[0] === '1') {
            info.lat = -Util_1.Util.round6(~parseInt(arr.substring(0, 32), 2) * 1e-6);
        }
        else {
            info.lat = Util_1.Util.round6(parseInt(arr.substring(0, 32), 2) * 1e-6);
        }
        info.gridLat = Util_1.Util.round6(parseInt(arr.substring(32, 48), 2) * 1e-6);
        // 先頭ビットが1の場合は、マイナス値なので補数を取る
        if (arr.substring(40, 72)[0] === '1') {
            info.lng = -Util_1.Util.round6(~parseInt(arr.substring(48, 80), 2) * 1e-6);
        }
        else {
            info.lng = Util_1.Util.round6(parseInt(arr.substring(48, 80), 2) * 1e-6);
        }
        info.gridLng = Util_1.Util.round6(parseInt(arr.substring(80, 96), 2) * 1e-6);
        var unit = parseInt(arr.substring(96, 108), 2);
        var grid = {
            north: info.lat + info.gridLat,
            south: info.lat,
            east: info.lng + info.gridLng,
            west: info.lng,
        };
        return { bounds: grid, unit: unit };
    };
    ////////////////////////
    // GridAddressからGridInfoをデコード
    Decode.gridIdTo3DLocation = function (address) {
        var info = { lat: 0, gridLat: 0, lng: 0, gridLng: 0 };
        var arr = '';
        // Addressを数値に変換->２進数に変換
        try {
            for (var i = 0; i < address.length; i++) {
                var str = address[i];
                arr += Util_1.Util.paddingleft(parseInt(this.base64Dec[str].toString()).toString(2), '0', 6);
            }
        }
        catch (err) {
            console.error(err);
        }
        // 先頭ビットが1の場合は、マイナス値なので補数を取る
        if (arr.substring(0, 32)[0] === '1') {
            info.lat = -Util_1.Util.round6(~parseInt(arr.substring(0, 32), 2) * 1e-6);
        }
        else {
            info.lat = Util_1.Util.round6(parseInt(arr.substring(0, 32), 2) * 1e-6);
        }
        info.gridLat = Util_1.Util.round6(parseInt(arr.substring(32, 48), 2) * 1e-6);
        // 先頭ビットが1の場合は、マイナス値なので補数を取る
        if (arr.substring(40, 72)[0] === '1') {
            info.lng = -Util_1.Util.round6(~parseInt(arr.substring(48, 80), 2) * 1e-6);
        }
        else {
            info.lng = Util_1.Util.round6(parseInt(arr.substring(48, 80), 2) * 1e-6);
        }
        info.gridLng = Util_1.Util.round6(parseInt(arr.substring(80, 96), 2) * 1e-6);
        var unit = parseInt(arr.substring(111, 120), 2);
        var oneUnitAlts = Encode_1.default.getDivAltitude(unit);
        var altitude = parseInt(arr.substring(96, 111), 2) + oneUnitAlts[0]; // Offset補正
        var grid = {
            north: info.lat + info.gridLat,
            south: info.lat,
            east: info.lng + info.gridLng,
            west: info.lng,
        };
        return { bounds: grid, altitude: { lower: altitude, upper: altitude + unit }, unit: unit };
    };
    Decode.base64Dec = {
        A: 0, B: 1, C: 2, D: 3, E: 4, F: 5, G: 6, H: 7, I: 8, J: 9,
        K: 10, L: 11, M: 12, N: 13, O: 14, P: 15, Q: 16, R: 17,
        S: 18, T: 19, U: 20, V: 21, W: 22, X: 23, Y: 24, Z: 25,
        a: 26, b: 27, c: 28, d: 29, e: 30, f: 31, g: 32, h: 33,
        i: 34, j: 35, k: 36, l: 37, m: 38, n: 39, o: 40, p: 41,
        q: 42, r: 43, s: 44, t: 45, u: 46, v: 47, w: 48, x: 49,
        y: 50, z: 51, '0': 52, '1': 53, '2': 54, '3': 55, '4': 56,
        '5': 57, '6': 58, '7': 59, '8': 60, '9': 61, '+': 62, '/': 63,
    };
    return Decode;
}());
exports.default = Decode;
