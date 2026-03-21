const path = require("path");
const CopyPlugin = require("copy-webpack-plugin");

module.exports = {
  entry: {
    functions: "./src/functions.ts",
  },
  output: {
    filename: "[name].js",
    path: path.resolve(__dirname, "dist"),
    clean: true,
  },
  resolve: {
    extensions: [".ts", ".js"],
  },
  module: {
    rules: [
      {
        test: /\.ts$/,
        use: "ts-loader",
        exclude: /node_modules/,
      },
    ],
  },
  experiments: {
    asyncWebAssembly: true,
  },
  plugins: [
    new CopyPlugin({
      patterns: [
        { from: "manifest.xml", to: "manifest.xml" },
        { from: "assets", to: "assets", noErrorOnMissing: true },
        // Copy the WASM package built by wasm-pack.
        {
          from: "../../rust/quantum_engine/pkg",
          to: "quantum_engine",
          noErrorOnMissing: true,
        },
      ],
    }),
  ],
};
