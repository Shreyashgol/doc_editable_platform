import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./store/auth";
import { CanvasPage } from "./pages/CanvasPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GraphPage } from "./pages/GraphPage";
import { LoginPage } from "./pages/LoginPage";
import { SearchPage } from "./pages/SearchPage";
import { UploadPage } from "./pages/UploadPage";

function Shell({ children }: { children: React.ReactNode }) {
  const clear = useAuth((s) => s.clear);
  return (
    <div style={{ fontFamily: "system-ui", margin: 0 }}>
      <nav style={{ display: "flex", gap: 16, padding: 12, borderBottom: "1px solid #ddd" }}>
        <strong>Document AI</strong>
        <Link to="/">Dashboard</Link>
        <Link to="/upload">Upload</Link>
        <Link to="/search">Search</Link>
        <button style={{ marginLeft: "auto" }} onClick={clear}>Sign out</button>
      </nav>
      <main style={{ padding: 16 }}>{children}</main>
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.accessToken);
  if (!token) return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/upload" element={<RequireAuth><UploadPage /></RequireAuth>} />
      <Route path="/documents/:id/canvas" element={<RequireAuth><CanvasPage /></RequireAuth>} />
      <Route path="/documents/:id/graph" element={<RequireAuth><GraphPage /></RequireAuth>} />
      <Route path="/search" element={<RequireAuth><SearchPage /></RequireAuth>} />
    </Routes>
  );
}
