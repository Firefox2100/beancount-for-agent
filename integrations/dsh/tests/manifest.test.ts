// The bundle conventions DSH's own shipped bundles follow: what the manifest points at must exist, and the catalogue
// metadata (title, description, detail page, icon) must be there for every language the harness offers.
import { readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

import { DSH_ENGINES, DSH_PACKAGE_PEERS, DSH_RELEASES } from "../scripts/dsh-compat.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (path: string) => readFileSync(join(root, path), "utf8");
const manifest = JSON.parse(read("package.json"));
const exists = (path: string) => {
  try {
    const stats = statSync(join(root, path));
    return stats.isFile() || stats.isDirectory();
  } catch {
    return false;
  }
};

/** The languages the harness ships dictionaries for. */
const LANGUAGES = ["de", "en", "es", "fr", "ja", "pt", "ru", "zh"];

describe("the manifest declares a bundle the host can load", () => {
  test("it is a module bundle with a patch the loader can apply", () => {
    expect(manifest.type).toBe("module");
    expect(manifest.dsh.bundle.patch).toBe("./cordis.patch.yml");
    expect(exists("cordis.patch.yml")).toBe(true);
    expect(manifest.dsh.client.platform).toBe("web");
    expect(manifest.main).toBe("lib/index.js");
  });

  test("it exports what DSH imports, including the sources and the patch", () => {
    expect(Object.keys(manifest.exports)).toEqual(
      expect.arrayContaining([".", "./package.json", "./cordis.patch.yml", "./locale/*.json", "./src/*", "./client"]),
    );
    for (const target of Object.values(manifest.exports)) {
      const path = String(target);
      if (!path.includes("*")) expect(exists(path), path).toBe(true);
    }
  });

  test("it packs every runtime file and the catalogue metadata", () => {
    expect(manifest.files).toEqual(
      expect.arrayContaining(["icon.svg", "locale/*.json", "lib/index.js", "lib/client.js", "cordis.patch.yml", "docs", "src"]),
    );
    expect(exists("lib/index.js")).toBe(true);
    expect(exists("lib/client.js")).toBe(true);
  });

  test("it installs on the releases the compatibility list names, and stops before the next patch line", () => {
    expect(manifest.engines.dsh).toBe(DSH_ENGINES);
    expect(manifest.engines.dsh).toContain(`>=${DSH_RELEASES[0]} `);
    // `<0.2.3-0` is the lowest pre-release of the next line: a plain `<0.2.3` would admit its alphas.
    expect(manifest.engines.dsh).toMatch(/<[^ ]+-0$/);
    for (const [name, range] of Object.entries(manifest.peerDependencies)) {
      if (name.startsWith("@deepseek-ai/dsh")) expect(range).toBe(DSH_PACKAGE_PEERS);
    }
  });
});

describe("the catalogue shows a title, a description and a detail page in every language", () => {
  test("every language has a catalogue entry", () => {
    for (const language of LANGUAGES) {
      const meta = JSON.parse(read(`locale/${language}.json`)).meta;
      expect(meta.title, language).toBe("Beancount");
      expect(typeof meta.description, language).toBe("string");
      expect(meta.description.length, language).toBeGreaterThan(20);
    }
  });

  test("every detail path points at a document that exists and holds exactly one image", () => {
    for (const language of LANGUAGES) {
      const detail = JSON.parse(read(`locale/${language}.json`)).meta.detail;
      expect(detail, language).toMatch(/^docs\/DETAIL(\.zh)?\.md$/);
      expect(exists(detail), language).toBe(true);
      const images = read(detail).match(/!\[[^\]]*\]\([^)]*\)/g) ?? [];
      expect(images, language).toHaveLength(1);
      const match = /!\[([^\]]*)\]\(([^)]*)\)/.exec(images[0] ?? "");
      expect(match, language).not.toBeNull();
      const alt = match?.[1] ?? "";
      const image = match?.[2] ?? "";
      expect(alt.length, language).toBeGreaterThan(20);
      expect(exists(join(dirname(detail), image)), image).toBe(true);
    }
  });

  test("the preview is artwork the detail page can frame: 640 by 300, no text and no script", () => {
    const preview = read("docs/preview.svg");
    expect(preview).toContain('viewBox="0 0 640 300"');
    expect(preview).not.toMatch(/<text|<script|<foreignObject|@font-face/);
    expect(statSync(join(root, "docs/preview.svg")).size).toBeLessThan(1024 * 1024);
  });

  test("the icon sits inside the package and is small enough for the plugin list", () => {
    expect(manifest.icon).toBe("./icon.svg");
    expect(exists("icon.svg")).toBe(true);
    expect(statSync(join(root, "icon.svg")).size).toBeLessThan(256 * 1024);
  });
});
