// Web Worker: runs the embedding model off the main thread so the page never
// freezes during model init or inference. Loaded on demand by app.js only when
// the user turns on 🧠 의미검색. Communicates via postMessage:
//   { type:"load", id }            -> { type:"loaded", id }
//   { type:"embed", id, payload }  -> { type:"embed", id, vec:[...] }
//   progress/errors                -> { type:"progress"|"error", ... }
const MODEL = "Xenova/multilingual-e5-small";
const CDN = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2";

let extractorPromise = null;

async function getExtractor() {
  if (!extractorPromise) {
    extractorPromise = (async () => {
      const { pipeline, env } = await import(CDN);
      env.allowLocalModels = false; // fetch from the Hub, not same-origin
      return pipeline("feature-extraction", MODEL, {
        quantized: true,
        progress_callback: (p) => self.postMessage({ type: "progress", payload: p }),
      });
    })();
  }
  return extractorPromise;
}

self.onmessage = async (e) => {
  const { type, id, payload } = e.data || {};
  try {
    if (type === "load") {
      await getExtractor();
      self.postMessage({ type: "loaded", id });
    } else if (type === "embed") {
      const extractor = await getExtractor();
      const out = await extractor(payload, { pooling: "mean", normalize: true });
      // Plain array crosses the worker boundary cleanly (normalized -> dot = cosine).
      self.postMessage({ type: "embed", id, vec: Array.from(out.data) });
    }
  } catch (err) {
    extractorPromise = null; // let a later attempt retry from scratch
    self.postMessage({ type: "error", id, message: String((err && err.message) || err) });
  }
};
