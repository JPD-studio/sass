import { IGrid, IGrid3D } from "../models/Model";
export default class Decode {
    private static base64Dec;
    static gridIdToLatlng(address: string): IGrid;
    static gridIdTo3DLocation(address: string): IGrid3D;
}
