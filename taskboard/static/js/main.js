/** Entry point: mount the application. */
import { App } from "./app.js";
import { html, render } from "./ui.js";

render(html`<${App} />`, document.getElementById("app"));
