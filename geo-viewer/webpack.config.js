import path from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const _require = createRequire(import.meta.url);
const CopyWebpackPlugin = _require("copy-webpack-plugin");
const Dotenv = _require("dotenv-webpack");

export default {
  entry: "./src/main.ts",
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: [
          {
            loader: "ts-loader",
            options: {
              configFile: "tsconfig.webpack.json",
            },
          },
        ],
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: ["style-loader", "css-loader"],
      },
    ],
  },
  resolve: {
    extensions: [".tsx", ".ts", ".js"],
    extensionAlias: {
      ".js": [".ts", ".js"],
    },
  },
  output: {
    filename: "bundle.js",
    path: path.resolve(__dirname, "dist"),
    // CesiumJS が静的アセットを解決するためのパス
    publicPath: "/dist/",
  },
  plugins: [
    new Dotenv({ silent: true }),
    // CesiumJS の静的アセット (Workers, Assets, Widgets) をコピー
    new CopyWebpackPlugin({
      patterns: [
        {
          from: path.resolve(__dirname, "node_modules/cesium/Build/Cesium/Workers"),
          to: "Workers",
        },
        {
          from: path.resolve(__dirname, "node_modules/cesium/Build/Cesium/ThirdParty"),
          to: "ThirdParty",
        },
        {
          from: path.resolve(__dirname, "node_modules/cesium/Build/Cesium/Assets"),
          to: "Assets",
        },
        {
          from: path.resolve(__dirname, "node_modules/cesium/Build/Cesium/Widgets"),
          to: "Widgets",
        },
      ],
    }),
  ],
  // CesiumJS の CESIUM_BASE_URL を dist/ に設定
  amd: {
    toUrlUndefined: true,
  },
  experiments: {
    // top-level await を有効化
    topLevelAwait: true,
  },
  mode: "development",
  devtool: "source-map",
};
