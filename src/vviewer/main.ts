// Minimal viewer for method V only (vector standing picture). No Three.js.
import "../ui/theme.css";
import "../ui/app.css";
import "./vviewer.css";
import { VViewer } from "./vviewer";

declare const __BUILD_ID__: string;

const root = document.getElementById("app")!;
root.innerHTML = `
  <header class="container app-header">
    <span class="brand">vector-avator</span>
    <button class="status-pill" id="status" data-state="warn" aria-live="polite">
      <span class="dot" aria-hidden="true"></span><span id="status-text">◷ 読み込み中</span>
    </button>
  </header>
  <main class="container layout">
    <section class="card" aria-labelledby="controls-title">
      <h2 id="controls-title">操作</h2>
      <div id="controls"></div>
    </section>
    <section class="card" aria-labelledby="preview-title">
      <h2 id="preview-title">プレビュー</h2>
      <div class="preview" id="preview"></div>
      <p class="caption" id="preview-caption"></p>
    </section>
  </main>
  <footer class="container app-footer">
    ベクター立ち絵のビューアです。読み込んだファイルは外部へ送信しません。build ${__BUILD_ID__}
  </footer>`;
const $ = (id: string) => root.querySelector<HTMLElement>(`#${id}`)!;
const viewer = new VViewer({ controls: $("controls"), preview: $("preview"), status: $("status"), statusText: $("status-text"), caption: $("preview-caption") });
// used by the capture tools (tools/capture/sequence.mjs)
(window as unknown as { __viewer: VViewer }).__viewer = viewer;
