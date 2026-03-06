/** @type {import('jest').Config} */
export default {
  preset: "ts-jest",
  testEnvironment: "node",
  extensionsToTreatAsEsm: [".ts"],
  moduleNameMapper: {
    "^(\\.{1,2}/.*)\\.js$": "$1",
    // Three.js は ESM なので空モックに差し替え
    "^three$": "<rootDir>/tests/__mocks__/three.js",
  },
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        useESM: true,
        tsconfig: {
          module: "ESNext",
          moduleResolution: "bundler",
          rootDir: "../..",
        },
      },
    ],
  },
  testMatch: ["**/tests/**/*.test.ts"],
};
