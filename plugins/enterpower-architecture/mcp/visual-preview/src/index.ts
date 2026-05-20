#!/usr/bin/env node
/**
 * MCP server: visual-preview
 *
 * PURPOSE
 * Provides four MCP tools that manage a local Vite dev server serving the
 * interactive ArchiMate viewer, and a Puppeteer screenshot tool for
 * verification. the assistant calls these tools via the "preview" MCP server entry.
 *
 * TOOLS
 *   preview_start      — copy template, inject VIEWS data, start Vite, open browser
 *   preview_update     — replace VIEWS data in running project (Vite HMR refreshes)
 *   preview_screenshot — capture the live viewer via headless Puppeteer
 *   preview_stop       — shut down the Vite dev server
 *
 * LOCATION — mcp/visual-preview/
 * MCP servers have their own Node.js runtime and dependencies, so they live
 * under mcp/ separate from skills/ and templates/. Each server is a
 * self-contained package.
 *
 * RELATIONS
 * - Registered in:  .mcp.json (repo root) → "preview" server entry
 * - Invoked by:     skills/archimate-visual-composer/SKILL.md
 * - Template source: templates/archimate-viewer/ (copied to WORK_DIR on start)
 * - Hook consumer:  hooks/archimate-view-post-write.sh syncs template writes
 *                   to WORK_DIR so Vite HMR picks them up without a tool call
 * - Work directory: ~/.cache/archimate-preview/project/ (node_modules persist
 *                   across sessions to avoid repeated npm install)
 *
 * SETUP
 * Run once before first use: cd mcp/visual-preview && npm install
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { spawn, spawnSync, ChildProcess } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "../../..");
const TEMPLATE_DIR = join(REPO_ROOT, "templates/archimate-viewer");
const WORK_DIR = join(homedir(), ".cache/archimate-preview/project");
const PORT = 5173;
const PREVIEW_URL = `http://localhost:${PORT}`;

let viteProc: ChildProcess | null = null;

function ensureWorkDir(): void {
  mkdirSync(WORK_DIR, { recursive: true });
}

function syncTemplateFiles(): void {
  cpSync(TEMPLATE_DIR, WORK_DIR, {
    recursive: true,
    filter: (src) => !src.includes("node_modules"),
  });
}

// Replaces the INITIAL_VIEWS block in the template copy with the assistant's VIEWS data.
// the assistant sends "const VIEWS = { ... };" — this renames it to INITIAL_VIEWS to match
// the variable name the template's rendering logic depends on.
// The injection zone is delimited by sentinel comments @@VIEWS_START@@ / @@VIEWS_END@@
// so the regex cannot accidentally match the variable name inside JSX comments.
function injectViews(code: string): void {
  const file = join(WORK_DIR, "template.jsx");
  let content = readFileSync(file, "utf-8");

  let normalized = code.trimEnd();
  if (!normalized.startsWith("const")) {
    normalized = `const INITIAL_VIEWS = ${normalized}`;
  } else {
    normalized = normalized.replace(/^const VIEWS\s*=/, "const INITIAL_VIEWS =");
  }
  if (!normalized.endsWith(";")) normalized += ";";

  const START = "// @@VIEWS_START@@";
  const END = "// @@VIEWS_END@@";
  const startIdx = content.indexOf(START);
  const endIdx = content.indexOf(END);
  if (startIdx === -1 || endIdx === -1) {
    throw new Error("VIEWS injection sentinels (@@VIEWS_START@@ / @@VIEWS_END@@) not found in template.jsx — template may have changed.");
  }
  const updated =
    content.slice(0, startIdx + START.length) +
    "\n" + normalized + "\n" +
    content.slice(endIdx);
  writeFileSync(file, updated, "utf-8");
}

function ensureDeps(): void {
  if (!existsSync(join(WORK_DIR, "node_modules"))) {
    const result = spawnSync("npm", ["install"], {
      cwd: WORK_DIR,
      stdio: "inherit",
    });
    if (result.status !== 0) {
      throw new Error("npm install failed in preview work directory");
    }
  }
}

function stopVite(): void {
  if (viteProc) {
    viteProc.kill("SIGTERM");
    viteProc = null;
  }
}

function startVite(): Promise<string> {
  stopVite();
  return new Promise((resolve, reject) => {
    viteProc = spawn("npx", ["vite", "--port", String(PORT), "--strictPort"], {
      cwd: WORK_DIR,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let resolved = false;
    const finish = (url: string) => {
      if (!resolved) {
        resolved = true;
        resolve(url);
      }
    };

    viteProc.stdout?.on("data", (chunk: Buffer) => {
      if (chunk.toString().includes("localhost")) finish(PREVIEW_URL);
    });

    viteProc.on("error", (err) => {
      if (!resolved) reject(err);
    });

    // Fallback: resolve after 8 s regardless, Vite is likely ready by then
    setTimeout(() => finish(PREVIEW_URL), 8000);
  });
}

function openBrowser(url: string): void {
  const cmd =
    process.platform === "darwin" ? "open" :
    process.platform === "win32"  ? "start" :
    "xdg-open";
  spawn(cmd, [url], { detached: true, stdio: "ignore" }).unref();
}

// ── MCP server ───────────────────────────────────────────────

const server = new Server(
  { name: "visual-preview", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "preview_start",
      description:
        "Scaffold the ArchiMate viewer Vite project with the provided VIEWS data, start the dev server on port 5173, and open the browser.",
      inputSchema: {
        type: "object" as const,
        properties: {
          code: {
            type: "string",
            description: "JavaScript literal: const VIEWS = { ... };",
          },
        },
        required: ["code"],
      },
    },
    {
      name: "preview_update",
      description:
        "Hot-replace the VIEWS data in the running preview. Vite HMR refreshes the browser automatically.",
      inputSchema: {
        type: "object" as const,
        properties: {
          code: {
            type: "string",
            description: "Updated JavaScript literal: const VIEWS = { ... };",
          },
        },
        required: ["code"],
      },
    },
    {
      name: "preview_screenshot",
      description: "Take a screenshot of the current preview for verification.",
      inputSchema: {
        type: "object" as const,
        properties: {
          selector: {
            type: "string",
            description: "CSS selector to capture. Omit for full viewport.",
          },
          fullPage: {
            type: "boolean",
            description: "Capture full scrollable height (default: false).",
          },
        },
      },
    },
    {
      name: "preview_stop",
      description: "Stop the Vite dev server.",
      inputSchema: {
        type: "object" as const,
        properties: {},
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "preview_start": {
        if (!args?.code) throw new Error("Missing required argument: code");
        ensureWorkDir();
        syncTemplateFiles();
        injectViews(args.code as string);
        ensureDeps();
        const url = await startVite();
        openBrowser(url);
        return {
          content: [{ type: "text", text: `Preview running at ${url}` }],
        };
      }

      case "preview_update": {
        if (!viteProc) throw new Error("No preview running — call preview_start first.");
        if (!args?.code) throw new Error("Missing required argument: code");
        injectViews(args.code as string);
        return {
          content: [{ type: "text", text: "VIEWS updated. Vite HMR will refresh the browser." }],
        };
      }

      case "preview_screenshot": {
        const puppeteer = await import("puppeteer");
        const browser = await puppeteer.default.launch({ headless: true });
        try {
          const page = await browser.newPage();
          await page.setViewport({ width: 1440, height: 900 });
          await page.goto(PREVIEW_URL, { waitUntil: "networkidle2", timeout: 15000 });

          let screenshot: string;
          if (args?.selector) {
            const el = await page.$(args.selector as string);
            if (!el) throw new Error(`Selector not found: ${args.selector}`);
            screenshot = (await el.screenshot({ encoding: "base64" })) as string;
          } else {
            screenshot = (await page.screenshot({
              encoding: "base64",
              fullPage: !!(args?.fullPage),
            })) as string;
          }

          return {
            content: [
              { type: "image", data: screenshot, mimeType: "image/png" },
              { type: "text", text: "Screenshot captured (1440×900)." },
            ],
          };
        } finally {
          await browser.close();
        }
      }

      case "preview_stop": {
        stopVite();
        return {
          content: [{ type: "text", text: "Preview stopped." }],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
