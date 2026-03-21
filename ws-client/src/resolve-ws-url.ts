// ws-client/src/resolve-ws-url.ts
/**
 * ブラウザ環境用 WebSocket URL 解決。
 * 優先順位: URL query ?ws= → <meta name="ws-url"> → /websocket.json → hostname:8765
 */
export async function resolveWsUrl(): Promise<string> {
  // 1. URL クエリパラメータ ?ws=
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("ws");
  if (fromQuery) return fromQuery;

  // 2. <meta name="ws-url"> タグ
  const meta = document.querySelector<HTMLMetaElement>('meta[name="ws-url"]');
  if (meta?.content) return meta.content;

  // 3. /websocket.json (runtime 共通設定)
  try {
    const resp = await fetch("/websocket.json");
    if (resp.ok) {
      const json = await resp.json();
      if (json.websocket_url) return json.websocket_url;
    }
  } catch { /* fallback */ }

  // 4. デフォルト
  return `ws://${window.location.hostname}:8765`;
}
