import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const projectDirectory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: path.join(projectDirectory, "static-pages"),
  base: "./",
  publicDir: path.join(projectDirectory, "public"),
  plugins: [react()],
  build: {
    outDir: path.join(projectDirectory, "pages-dist"),
    emptyOutDir: true,
  },
});
