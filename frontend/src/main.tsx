import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { Display } from "./display/Display";
import "./styles/base.css";

// The admin UI is only loaded when needed, keeping the display bundle small.
const AdminApp = lazy(() => import("./admin/AdminApp"));
const SharePage = lazy(() => import("./share/SharePage").then((m) => ({ default: m.SharePage })));

function App() {
  const path = window.location.pathname;
  if (path.startsWith("/share")) {
    document.documentElement.classList.add("is-share");
    return (
      <Suspense fallback={null}>
        <SharePage />
      </Suspense>
    );
  }
  const isAdmin = path.startsWith("/admin") || path.startsWith("/login");
  document.documentElement.classList.add(isAdmin ? "is-admin" : "is-display");
  if (isAdmin) {
    return (
      <Suspense fallback={null}>
        <AdminApp />
      </Suspense>
    );
  }
  return <Display />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
