"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
var LatLng = /** @class */ (function () {
    function LatLng(a, b) {
        this._lat = NaN;
        this._lng = NaN;
        if (typeof (a) === 'number') {
            this._lat = a;
            if (typeof (b) === 'number')
                this._lng = b;
            else
                throw "latLng init err";
        }
        else {
            this._lat = a[0];
            this._lng = a[1];
        }
    }
    Object.defineProperty(LatLng.prototype, "lat", {
        get: function () {
            return this._lat;
        },
        set: function (lat) {
            this._lat = lat;
        },
        enumerable: false,
        configurable: true
    });
    Object.defineProperty(LatLng.prototype, "lng", {
        get: function () {
            return this._lng;
        },
        set: function (lng) {
            this._lng = lng;
        },
        enumerable: false,
        configurable: true
    });
    return LatLng;
}());
exports.default = LatLng;
