export interface MountPosition {
  lat: number;      // WGS84 緯度 [度]
  lng: number;      // WGS84 経度 [度]
  alt: number;      // WGS84 楕円体高 [m]（ジオイド高ではない。日本では楕円体高 ≈ ジオイド高 + 約37m）
}

export interface MountOrientation {
  heading: number;  // Euler 角 [度] (0=真北、時計回り正)
  pitch: number;    // Euler 角 [度] (0=水平、正=上向き)
  roll: number;     // Euler 角 [度] (0=水平、正=右傾き)
}

export interface SensorMount {
  position: MountPosition;
  orientation: MountOrientation;
  mounting_type: string;
}

export interface MeasurementError {
  position_m: number;       // GPS 計測誤差 3σ [m]
  orientation_deg: number;  // 角度キャリブレーション誤差 3σ [度]
  mounting_stability: "fixed" | "unstable";
}

export const DEFAULT_MOUNT: SensorMount = {
  position: { lat: 0, lng: 0, alt: 0 },
  orientation: { heading: 0, pitch: 0, roll: 0 },
  mounting_type: "pole_mounted",
};
