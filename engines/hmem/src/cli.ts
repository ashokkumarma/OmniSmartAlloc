// JSON-over-stdio front end for the H-MEM engine, used by the Python agent
// (src/memory/hmem.py). One request per process: read a JSON object from stdin,
// write one JSON object to stdout. State persists in <dir>/state.json and an
// append-only <dir>/ledger.jsonl.
//
//   {"op":"add","dir":"...","content":"...","source":"...","tags":[...],"namespace":"...","confidence":0.8,
//    "type":"preference","provenance":{"origin":"user_correction","label":"...","refs":["approval:abc"]}}
//   {"op":"query","dir":"...","text":"...","namespace":"...","topN":5,"threshold":0.05}
//   {"op":"feedback","dir":"...","id":"mem-1","kind":"helpful"}
//   {"op":"all","dir":"...","namespace":"..."}
//
// Run with Node 22.18+ / 23.6+ (built-in TypeScript type stripping): node src/cli.ts

import { HMEM, type FeedbackKind, type MemoryRecord } from "./hmem.ts";

const strip = (m: MemoryRecord) => {
  const { embedding: _e, ...rest } = m;
  return rest;
};

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString("utf-8");
}

async function main(): Promise<void> {
  const req = JSON.parse((await readStdin()) || "{}");
  if (!req.dir) throw new Error("dir is required");
  const mem = new HMEM({ persistDir: req.dir, actor: req.actor ?? "omnismartalloc" });
  let out: unknown;
  switch (req.op) {
    case "add": {
      const now = Date.now();
      const m = mem.add({
        content: req.content,
        source: req.source,
        type: req.type,
        layer: req.layer,
        tags: req.tags,
        confidence: req.confidence,
        namespace: req.namespace,
        provenance: req.provenance ? { learnedAt: now, ...req.provenance } : undefined,
      });
      out = { memory: strip(m) };
      break;
    }
    case "query": {
      const r = mem.query(req.text ?? "", { topN: req.topN, threshold: req.threshold, namespace: req.namespace });
      out = {
        memories: r.memories.map((s) => ({ relevance: Number(s.relevance.toFixed(4)), memory: strip(s.memory) })),
        context: r.context,
        trace: r.trace,
      };
      break;
    }
    case "feedback":
      out = { memory: strip(mem.feedback(req.id, req.kind as FeedbackKind)) };
      break;
    case "all":
      out = { memories: mem.store.all().filter((m) => !req.namespace || m.namespace === req.namespace).map(strip) };
      break;
    default:
      throw new Error(`unknown op ${req.op}`);
  }
  process.stdout.write(JSON.stringify(out));
}

main().catch((err) => {
  process.stderr.write(`hmem: ${(err as Error).message}\n`);
  process.exit(1);
});
