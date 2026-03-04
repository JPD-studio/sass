// ws-client/src/point-stream.ts
import type { PointData } from "./types.js";
import { WsConnection } from "./ws-connection.js";

/** 複数の WsConnection を束ねるマルチソースストリーム（将来拡張） */
export class PointStream {
  private _sources = new Map<string, WsConnection>();

  addSource(id: string, connection: WsConnection): void {
    this._sources.set(id, connection);
  }

  removeSource(id: string): void {
    this._sources.delete(id);
  }

  async *mergedFrames(): AsyncGenerator<{ sourceId: string; points: PointData[] }> {
    // 各ソースを並走させ、到着順に yield する
    const channels: Array<{ id: string; gen: AsyncGenerator<PointData[]> }> = [];
    for (const [id, conn] of this._sources) {
      channels.push({ id, gen: conn.frames() });
    }

    // シンプルな round-robin（将来は arrival-order マージに拡張）
    while (channels.length > 0) {
      for (let i = channels.length - 1; i >= 0; i--) {
        const ch = channels[i];
        const result = await ch.gen.next();
        if (result.done) {
          channels.splice(i, 1);
        } else {
          yield { sourceId: ch.id, points: result.value };
        }
      }
    }
  }
}
