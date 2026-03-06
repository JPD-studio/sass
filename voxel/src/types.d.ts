export type VoxelKey = string;
export interface VoxelState {
    count: number;
    lastUpdated: number;
}
export type VoxelSnapshot = Map<VoxelKey, VoxelState>;
export interface BackgroundStats {
    mean: number;
    stddev: number;
    samples: number;
}
export interface VoxelDiffEntry {
    key: VoxelKey;
    currentCount: number;
    backgroundMean: number;
    delta: number;
}
