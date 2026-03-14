export interface GeoViewerConfig {
  websocket_url: string;
  mount: {
    position: { lat: number; lng: number; alt: number };
    orientation: { heading: number; pitch: number; roll: number };
  };
}
