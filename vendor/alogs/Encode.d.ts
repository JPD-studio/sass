export default class Encode {
    protected static ONE_UNIT_GRID: number;
    protected static UNIT_MATER: number;
    protected static OneUnitLats: number[];
    protected static MaxAltitude: number;
    protected static base64Enc: string[];
    protected static unitList: number[];
    /**
     * 緯度・経度を 2D グリッド ID（住所）に変換する
     *
     * @param lat - 緯度（十進度）
     * @param lng - 経度（十進度）
     * @param gridUnit - グリッドサイズ（メートル単位、デフォルト 1m）
     * @returns グリッドID（例: "A-12-34"） 該当しない場合は空文字列
     */
    static LatLngToID(lat: number, lng: number, gridUnit?: number): string;
    /**
    * 指定位置の周辺グリッドライン（緯度・経度）を取得
    *
    * @param lat - 緯度
    * @param lng - 経度
    * @param unit - グリッド単位（メートル）
    * @param numOfLine - 線の数（上限1000）
    * @returns グリッド線リスト（オブジェクト形式）
    */
    static GridLine(lat: number, lng: number, unit?: number, numOfLine?: number): string;
    protected static getSplitIndex(list: {
        lat: number[];
        lng: number[];
        gridLat: number;
        gridLng: number;
    }, latIndex: number, lngIndex: number, lat: number, lng: number, unit: number): {
        splitLatIndex: number;
        splitLngIndex: number;
        splitList: {
            lat: number[];
            lng: number[];
            gridLat: number;
            gridLng: number;
        };
    };
    /**
     * 緯度経度高さ情報を3D IDに変換
     * @param lat
     * @param lng
     * @param alt
     */
    static LatLngTo3DID(lat: number, lng: number, alt: number, unit?: number): string;
    /**
     * 指定位置の周辺のGridLineの取得
     * @param lat
     * @param lng
     */
    static GridLine3D(lat: number, lng: number, alt: number, unit?: number, numOfLine?: number): string;
    /**
     * IDのセットの取得
     * @param basises
     */
    protected static getGridID(basises: any): {
        lat: number[];
        lng: number[];
        gridLat: number;
        gridLng: number;
    };
    protected static getGridLng(lat: number): number;
    protected static getBasis(latLng: {
        lat: number;
        lng: number;
    }): {
        lat: number;
        lng: number;
    }[] | undefined;
    protected static getAddress(latIndex: number, lngIndex: number, list: {
        lat: number[];
        lng: number[];
        gridLat: number;
        gridLng: number;
    }, unit: number): string;
    protected static getAddress3D(latIndex: number, lngIndex: number, aIndex: number, list: {
        lat: number[];
        lng: number[];
        gridLat: number;
        gridLng: number;
    }, oneUnitAlts: number[], unit: number): string;
    protected static grid2Address(lat: number, lng: number, gridLat: number, gridLng: number, unit: number): string;
    protected static grid2Address3D(lat: number, lng: number, gridLat: number, gridLng: number, altitude: number, unit: number): string;
    /**
     * 指定した value が arr[i] <= value < arr[i+1] に該当する i を返す。
     * 該当する区間がなければ -1 を返す。
     *
     * @param arr - 昇順にソートされた数値配列
     * @param value - 検索対象の数値
     * @returns 該当区間のインデックス i、該当なしは -1
     */
    protected static binarySearch1(arr: number[], value: number): number;
    /**
     * 2次元配列 arr に対し、arr[i][0] <= param < arr[i+1][0] を満たす i を返す。
     * 該当しない場合は -1 を返す。
     *
     * @param grid - 先頭要素が数値の2次元配列（昇順ソート済）
     * @param value - 検索対象の数値
     * @returns 区間のインデックス i（arr[i][0] <= value < arr[i+1][0]）、なければ -1
     */
    protected static binarySearch2(grid: number[][], value: number): number;
    protected static getDivEquator(): number[];
    static getDivAltitude(unit: number): number[];
    protected static OneUnitLngs: number[][];
}
