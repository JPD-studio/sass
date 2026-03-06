export default class LatLng {
    private _lat;
    private _lng;
    constructor(pt: number[]);
    constructor(lat: number, lng: number);
    get lat(): number;
    get lng(): number;
    set lat(lat: number);
    set lng(lng: number);
}
