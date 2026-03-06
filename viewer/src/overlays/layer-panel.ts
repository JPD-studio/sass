// viewer/src/overlays/layer-panel.ts

import type { FrameDispatcher } from "../layers/frame-dispatcher.js";

export class LayerPanel {
  private _container: HTMLElement;

  constructor(parent: HTMLElement, dispatcher: FrameDispatcher) {
    this._container = document.createElement("div");
    this._container.className = "layer-panel";
    this._container.innerHTML = "<strong>表示レイヤー</strong>";

    for (const layer of dispatcher.layers) {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = layer.enabled;
      checkbox.addEventListener("change", () =>
        dispatcher.toggle(layer.name),
      );
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(` ${layer.label}`));
      this._container.appendChild(label);
    }

    parent.appendChild(this._container);
  }
}
