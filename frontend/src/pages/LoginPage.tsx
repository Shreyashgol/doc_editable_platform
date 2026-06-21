import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAuth } from "@/store/auth";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setTokens = useAuth((s) => s.setTokens);
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (isRegister) await api.register(email, password);
      const tokens = await api.login(email, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      navigate("/");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Authentication failed");
    }
  }

  return (
    <div style={{ maxWidth: 320, margin: "80px auto", fontFamily: "system-ui" }}>
      <h2>{isRegister ? "Create account" : "Sign in"}</h2>
      <form onSubmit={submit} style={{ display: "grid", gap: 8 }}>
        <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input
          placeholder="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit">{isRegister ? "Register & sign in" : "Sign in"}</button>
      </form>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <button onClick={() => setIsRegister((v) => !v)} style={{ marginTop: 8 }}>
        {isRegister ? "Have an account? Sign in" : "Need an account? Register"}
      </button>
    </div>
  );
}
