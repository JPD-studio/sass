"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Util = void 0;
var Util = /** @class */ (function () {
    function Util() {
    }
    /**
     * 左パディング処理
     * @param val
     * @param char
     * @param length
     */
    Util.paddingleft = function (val, char, length) {
        var leftval = '';
        for (; leftval.length < length; leftval += char)
            ;
        return (leftval + val).slice(-length);
    };
    /**
     * 少数第6位に四捨五入
     * @param num
     */
    Util.round6 = function (num) {
        return Math.round(num * 1e6) / 1e6;
    };
    /**
     * 乱数を取得
     * @param max
     */
    Util.getRandomInt = function (max) {
        return Math.floor(Math.random() * Math.floor(max));
    };
    /**
     * 現在時間を取得
     */
    Util.now = function () {
        var date = new Date();
        // unix Timeで計算する。
        return Math.floor(date.getTime() / 1000);
    };
    return Util;
}());
exports.Util = Util;
