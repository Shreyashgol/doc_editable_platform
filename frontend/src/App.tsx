import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ThemeToggle } from "./components/ThemeToggle";
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
    <>
      <nav className="app-nav">
        <span className="brand"><span className="dot" /> Document AI</span>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/upload">Upload</NavLink>
        <NavLink to="/search">Search</NavLink>
        <span className="spacer" />
        <ThemeToggle />
        <button className="btn btn--ghost" onClick={clear}>Sign out</button>
      </nav>
      <main className="app-main">{children}</main>
    </>
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
