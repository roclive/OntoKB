import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { createReadStream, existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { basename, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { platform } from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "web");
const port = Number(process.env.PORT || 5173);

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".mp4": "video/mp4",
  ".srt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
};

const planFiles = new Set([
  "clip_plan.csv",
  "remove_ranges.txt",
  "shorts_plan.csv",
  "cut_plan_new.csv",
]);
const mediaFiles = new Set([".mp4", ".srt"]);
const commandScripts = new Set([
  "cut_plan.py",
  "remove_ranges.py",
  "make_shorts.py",
  "generate_srt.py",
  "burn_existing_srt.py",
  "burn_vertical_srt.py",
]);

function safePath(urlPath) {
  const clean = decodeURIComponent(urlPath.split("?")[0]);
  const requested = clean === "/" ? "/index.html" : clean;
  const resolved = normalize(join(root, requested));
  if (resolved !== root && !resolved.startsWith(root + sep)) return null;
  return resolved;
}

function safeWorkspaceFile(filename, allowedExts, workspace = __dirname) {
  const clean = basename(String(filename || ""));
  const extension = extname(clean).toLowerCase();
  if (!clean || !allowedExts.has(extension)) {
    throw new Error(`Unsupported file: ${filename}`);
  }
  const resolved = normalize(join(workspace, clean));
  if (resolved !== workspace && !resolved.startsWith(workspace + sep)) {
    throw new Error(`Unsafe file path: ${filename}`);
  }
  return { name: clean, path: resolved, ext: extension };
}

function readRequestBody(req, limit = 2_000_000) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > limit) {
        reject(new Error("Request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

function sendJson(res, status, payload) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\\''")}'`;
}

function appleScriptString(value) {
  return `"${String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

function validateCommand(command) {
  if (!command || command.includes("\n") || command.includes("\r")) {
    throw new Error("Invalid command");
  }
  const match = command.match(/^python3\s+([^\s]+)\b/);
  if (!match || !commandScripts.has(match[1])) {
    throw new Error("Only npocut python commands can be run");
  }
}

function openTerminal(command) {
  if (platform() !== "darwin") {
    throw new Error("Terminal launch is currently implemented for macOS only");
  }
  validateCommand(command);
  const venvBin = join(__dirname, ".venv", "bin");
  const shellCommand = [
    `cd ${shellQuote(__dirname)}`,
    `export PATH=${shellQuote(`${venvBin}:$PATH`)}`,
    command,
  ].join(" && ");
  const script = [
    'tell application "Terminal"',
    "activate",
    `do script ${appleScriptString(shellCommand)}`,
    "end tell",
  ].join("\n");
  const child = spawn("osascript", ["-e", script], {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

export function createAppServer({ workspace = __dirname, runCommand = openTerminal, token, onSave = () => {} } = {}) {
  return createServer(async (req, res) => {
  if (req.method === "POST" && token && req.headers["x-npocut-token"] !== token) {
    sendJson(res, 403, { error: "Unauthorized request" });
    return;
  }
  if (req.method === "POST" && req.url === "/api/advanced-cut") {
    sendJson(res, 410, {
      error: "Advanced Cut now marks subtitle rows and exports a reversed keep plan: cut_plan_new.csv.",
    });
    return;
  }

  if (req.method === "POST" && req.url === "/api/run-command") {
    try {
      const payload = JSON.parse(await readRequestBody(req) || "{}");
      const command = String(payload.command || "").trim();
      await runCommand(command);
      sendJson(res, 200, { ok: true, cwd: workspace, command });
    } catch (error) {
      sendJson(res, 500, { error: error.message || "Run failed" });
    }
    return;
  }

  if (req.method === "POST" && req.url === "/api/export-plan") {
    try {
      const payload = JSON.parse(await readRequestBody(req) || "{}");
      const filename = basename(String(payload.filename || ""));
      const content = String(payload.content || "");
      if (!planFiles.has(filename)) {
        sendJson(res, 400, { error: "Unsupported plan filename" });
        return;
      }

      const outputPath = join(workspace, filename);
      await writeFile(outputPath, content, "utf8");
      onSave(filename, outputPath);
      sendJson(res, 200, { ok: true, path: outputPath });
    } catch (error) {
      sendJson(res, 500, { error: error.message || "Export failed" });
    }
    return;
  }

  if (req.method === "POST" && req.url === "/api/save-srt") {
    try {
      const payload = JSON.parse(await readRequestBody(req, 10_000_000) || "{}");
      const srt = safeWorkspaceFile(payload.filename, new Set([".srt"]), workspace);
      const content = String(payload.content || "");
      const outputPath = join(workspace, srt.name);
      await writeFile(outputPath, content, "utf8");
      onSave(srt.name, outputPath);
      sendJson(res, 200, { ok: true, path: outputPath, filename: srt.name });
    } catch (error) {
      sendJson(res, 500, { error: error.message || "SRT save failed" });
    }
    return;
  }

  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405);
    res.end("Method not allowed");
    return;
  }

  if (req.url?.startsWith("/media/")) {
    try {
      const name = decodeURIComponent(req.url.split("?")[0].replace(/^\/media\//, ""));
      const media = safeWorkspaceFile(name, mediaFiles, workspace);
      if (!existsSync(media.path)) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }
      res.writeHead(200, {
        "Content-Type": contentTypes[media.ext] || "application/octet-stream",
        "Cache-Control": "no-store",
      });
      if (req.method === "HEAD") {
        res.end();
        return;
      }
      createReadStream(media.path).pipe(res);
    } catch (error) {
      res.writeHead(400);
      res.end(error.message || "Bad request");
    }
    return;
  }

  let filePath;
  try { filePath = safePath(req.url || "/"); }
  catch { res.writeHead(400); res.end("Bad request"); return; }
  if (!filePath) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  try {
    const data = await readFile(filePath);
    res.writeHead(200, {
      "Content-Type": contentTypes[extname(filePath)] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
  });
}

function listen(candidatePort) {
  const server = createAppServer();
  server.once("error", (error) => {
    if (error.code === "EADDRINUSE" && candidatePort < port + 20) {
      console.log(`Port ${candidatePort} is busy, trying ${candidatePort + 1}`);
      listen(candidatePort + 1);
      return;
    }
    throw error;
  });

  server.listen(candidatePort, "127.0.0.1", () => {
    console.log(`npocut UI running at http://localhost:${candidatePort}`);
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) listen(port);
