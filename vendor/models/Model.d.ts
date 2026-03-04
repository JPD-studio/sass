/**
 * 2D Grid インターフェース
 */
export interface IGrid {
    bounds: {
        north: number;
        south: number;
        east: number;
        west: number;
    };
    unit: number;
}
/**
 * 3D Grid インターフェース
 */
export interface IGrid3D {
    bounds: {
        north: number;
        south: number;
        east: number;
        west: number;
    };
    altitude: {
        upper: number;
        lower: number;
    };
    unit: number;
}
export interface ILatLng {
    lat: number;
    lng: number;
}
