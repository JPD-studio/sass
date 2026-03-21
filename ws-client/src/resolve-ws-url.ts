// ws-client/src/resolve-ws-url.ts
/**
 * ブラウザ環境用 WebSocket URL 解決。
 * 優先順位: URL query ?ws= → <meta name="ws-url"> → hostname:8765
 */
export async function resolveWsUrl(): Promise<string> {
  // 1. URL クエリパラメータ ?ws=
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("ws");
  if (fromQuery) return fromQuery;

  // 2. <meta name="ws-url"> タグ
  const meta = document.querySelector<HTMLMetaElement>('meta[name="ws-url"]');
  if (meta?.content) return meta.content;

  // 3. デフォルト: アクセス元ホスト名を使用（リモートIPからも正しく接続）
  return `ws://${window.location.hostname}:8765`;
}
