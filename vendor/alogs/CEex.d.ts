import LatLng from '../models/LatLng';
import { IGrid } from '../models/Model';
import Encode from './Encode';
export default class CEex extends Encode {
    /**
     * 2点で指定される矩形の範囲のGridIDの一覧を取得
     * @param latLng1
     * @param latLng2
     * @returns 2点で指定される矩形の範囲のGridIDの一覧
     */
    static getAreaIDs(latLng1: LatLng, latLng2: LatLng, unit: number): {
        id: string;
        grid: IGrid;
    }[];
    /**
     * 多角形中に含まれるの空間IDの取得
     * @param polygon 多角形
     * @param unit 単位長さ
     * @returns 多角形中に含まれるの空間ID
     */
    static getContainPoygonIDs(polygon: LatLng[], unit: number): {
        id: string;
        grid: IGrid;
    }[];
    /**
   * 線に接触するの空間IDの取得
   * @param line 線
   * @param unit 単位長さ
   * @returns 多角形中に含まれるの空間ID
   */
    static getHitLineIDs(line: LatLng[], unit: number): {
        id: string;
        grid: IGrid;
    }[];
    /**
     * 特定の座標を基準にして、指定したブロック数のGridIDを取得
     * @param latlng 基準座標
     * @param alt 高度
     * @param unit 単位長さ
     * @param numOf 周辺ブロック数
     * @return 指定したブロック一覧
     */
    static getGrid3IDs(latlng: LatLng, alt: number, unit: number, numOf: number): {
        center: any;
        elements: any[];
    };
}
