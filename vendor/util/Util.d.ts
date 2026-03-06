export declare class Util {
    /**
     * 左パディング処理
     * @param val
     * @param char
     * @param length
     */
    static paddingleft(val: string, char: string, length: number): string;
    /**
     * 少数第6位に四捨五入
     * @param num
     */
    static round6(num: number): number;
    /**
     * 乱数を取得
     * @param max
     */
    static getRandomInt(max: number): number;
    /**
     * 現在時間を取得
     */
    static now(): number;
}
