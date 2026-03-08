import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
              // .js 拡張子のインポートを .ts ファイルとして解決
              allowTsInNodeModules: false,
            },
          },
        ],
        exclude: /node_modules/,
      },
      {
        // viewer が "type":"module" のため CJS vendor が ESM 扱いされ
        // exports is not defined になる問題を回避
        test: /[/\\]vendor[/\\].*\.js$/,
        type: "javascript/auto",
      },
    ],
  },
  resolve: {
    extensions: [".tsx", ".ts", ".js"],
    // ws-client / voxel の相対インポートを解決
    extensionAlias: {
      ".js": [".ts", ".js"],
    },
  },
  output: {
    filename: "bundle.js",
    path: path.resolve(__dirname, "dist"),
  },
  mode: "development",
  devtool: false,  // eval devtool は大規模 CJS ベンダーモジュールで問題が起きるため無効化
};
