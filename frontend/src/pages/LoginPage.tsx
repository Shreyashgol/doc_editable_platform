import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api } from "@/api/client";
import { useAuth } from "@/store/auth";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setTokens = useAuth((s) => s.setTokens);
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (isRegister) await api.register(email, password);
      const tokens = await api.login(email, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      navigate("/");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span className="brand"><span className="dot" /> Document AI</span>
          <ThemeToggle />
        </div>
        <h2 style={{ marginTop: 16 }}>{isRegister ? "Create account" : "Sign in"}</h2>
        <form onSubmit={submit} className="stack">
          <div className="field">
            <span className="label">Email</span>
            <input className="input" type="email" placeholder="you@company.com"
              value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <span className="label">Password</span>
            <input className="input" type="password" placeholder="••••••••"
              value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? "…" : isRegister ? "Register & sign in" : "Sign in"}
          </button>
        </form>
        {error && <p className="error-text">{error}</p>}
        <button className="btn btn--ghost" style={{ marginTop: 10, width: "100%" }}
          onClick={() => setIsRegister((v) => !v)}>
          {isRegister ? "Have an account? Sign in" : "Need an account? Register"}
        </button>
      </div>
    </div>
  );
}
