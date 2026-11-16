import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App, preloadPage } from "./App";
import "./styles.css";

// the opened page's own file first (a few KB, asked for at once): it then shows in the first render, with no skeleton
void preloadPage(window.location.pathname).then(() =>
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  ),
);
