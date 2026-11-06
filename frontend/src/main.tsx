import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { Display } from "./display/Display";
import "./styles/base.css";

// The admin UI is only loaded when needed, keeping the display bundle small.
const AdminApp = lazy(() => import("./admin/AdminApp"));

function App() {
  const path = window.location.pathname;
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
